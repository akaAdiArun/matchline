"""Compare invoice extractors against a fixed, held-out synthetic set."""

import argparse
import json
import os
import subprocess
from decimal import Decimal
from functools import partial
from pathlib import Path
from statistics import median
from time import perf_counter

import invoice_ocr
import vision_invoice
from matching import match


ROOT = Path(__file__).resolve().parent
EVALUATION = ROOT / "evaluation"
WARMUP = ROOT / "examples/scans/clean.png"
FIELDS = tuple(vision_invoice.PROPERTIES)


def load_cases(directory):
    cases = json.loads((directory / "cases.json").read_text(encoding="utf-8"), parse_float=Decimal)
    if not cases or len({case["image"] for case in cases}) != len(cases):
        raise ValueError("Evaluation requires a nonempty manifest with unique images.")
    for case in cases:
        name = case["image"]
        if Path(name).name != name or not (directory / "images" / name).is_file():
            raise ValueError(f"Invalid or missing benchmark image: {name}")
        if set(case["invoice"]) != set(FIELDS):
            raise ValueError(f"Unexpected ground-truth fields for {name}.")
        oracle = match(case["invoice"], case["purchase_order"], case["delivery_receipt"],
                       require_invoice_number=True)
        if oracle["status"] != case["expected_status"]:
            raise ValueError(f"Ground truth and expected decision disagree for {name}.")
    return cases


def extract_tesseract(image):
    fields = invoice_ocr.extract_invoice(image)["fields"]
    return {
        "values": {name: field["value"] for name, field in fields.items()},
        "issues": {name: field["issue"] for name, field in fields.items() if field["issue"]},
        "ocr_lines": {
            name: [entry["line_text"] for entry in field["observations"]]
            for name, field in fields.items()
        },
    }


def score(rows):
    by_field = {}
    readable = {"correct": 0, "total": 0}
    unreadable = {"correct": 0, "total": 0}
    for field in FIELDS:
        correct = 0
        for row in rows:
            truth = row["expected_fields"][field]
            hit = row["extraction"]["values"][field] == truth
            correct += hit
            bucket = unreadable if truth is None else readable
            bucket["total"] += 1
            bucket["correct"] += hit
        by_field[field] = {"correct": correct, "total": len(rows)}

    return {
        "field_accuracy": {
            "correct": readable["correct"] + unreadable["correct"],
            "total": readable["total"] + unreadable["total"],
        },
        "by_field": by_field,
        "readable_fields": readable,
        "unreadable_fields": unreadable,
        "decision_accuracy": {
            "correct": sum(row["status"] == row["expected_status"] for row in rows),
            "total": len(rows),
        },
        "incorrect_matches": {
            "count": sum(
                row["status"] == "matched" and row["expected_status"] != "matched" for row in rows
            ),
            "should_not_match": sum(row["expected_status"] != "matched" for row in rows),
        },
        "review": {"count": sum(row["status"] == "needs_review" for row in rows), "total": len(rows)},
        "median_ms": round(median(row["latency_ms"] for row in rows), 1),
    }


def run_extractor(name, extract, cases, image_directory):
    print(f"{name}: warming up on a development scan.", flush=True)
    extract(WARMUP)
    rows = []
    for case in cases:
        start = perf_counter()
        extraction = extract(image_directory / case["image"])
        decision = match(extraction["values"], case["purchase_order"], case["delivery_receipt"],
                         require_invoice_number=True)
        latency_ms = (perf_counter() - start) * 1000
        rows.append({
            "image": case["image"],
            "layout": case["layout"],
            "condition": case["condition"],
            "expected_fields": case["invoice"],
            "expected_status": case["expected_status"],
            "extraction": extraction,
            "status": decision["status"],
            "reason": decision["reason"],
            "latency_ms": round(latency_ms, 2),
        })
        print(f"  {case['image']}: {decision['status']} ({latency_ms:.1f} ms)", flush=True)
    metrics = score(rows)
    print(json.dumps(metrics, indent=2), flush=True)
    return {"metrics": metrics, "documents": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vision", action="store_true", help="Also run the local Qwen3-VL server")
    parser.add_argument("--port", type=int, default=vision_invoice.DEFAULT_PORT,
                        help="Local llama.cpp server port")
    parser.add_argument("--output", type=Path, help="Write per-document results and metrics as JSON")
    args = parser.parse_args()

    try:
        cases = load_cases(EVALUATION)
        tesseract = os.environ.get(invoice_ocr.OCR_EXE_ENV, "tesseract")
        version = subprocess.check_output([tesseract, "--version"], text=True, timeout=10)
        baseline = run_extractor("Tesseract", extract_tesseract, cases, EVALUATION / "images")
        baseline["version"] = version.splitlines()[0]
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))

    report = {"benchmark": "held-out synthetic invoices", "tesseract": baseline}
    if args.vision:
        try:
            report["qwen3_vl_2b"] = run_extractor(
                "Qwen3-VL-2B",
                partial(vision_invoice.extract_invoice, port=args.port),
                cases,
                EVALUATION / "images",
            )
        except RuntimeError as error:
            report["vision_error"] = str(error)
            print(f"Vision benchmark unavailable: {error}", flush=True)

    if args.output:
        args.output.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    return int("vision_error" in report)


if __name__ == "__main__":
    raise SystemExit(main())
