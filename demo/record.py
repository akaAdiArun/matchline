"""Refresh the demo recordings by running the real Matchline CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

from invoice_ocr import OCR_EXE_ENV


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "clean": ("clean.png", "receipt.json", "matched"),
    "short": ("short-delivery.png", "receipt-short.json", "mismatch"),
    "unreadable": ("quantity-only-obscured.png", "receipt.json", "needs_review"),
}


def main():
    tesseract = os.environ.get(OCR_EXE_ENV, "tesseract")
    version = subprocess.check_output([tesseract, "--version"], text=True).splitlines()[0]
    recordings = {}
    for name, (scan, receipt, status) in CASES.items():
        output = subprocess.check_output(
            [
                sys.executable, "-m", "matchline", "--invoice-image", f"examples/scans/{scan}",
                "examples/purchase-order.json", f"examples/{receipt}",
            ],
            cwd=ROOT,
            text=True,
        )
        decision = json.loads(output)
        if decision["status"] != status:
            raise SystemExit(f"{scan} produced {decision['status']}, expected {status}.")
        recordings[name] = decision

    path = ROOT / "demo/recordings.json"
    path.write_text(
        json.dumps({"engine": version, "cases": recordings}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Recorded three Matchline CLI decisions in demo/recordings.json.")


if __name__ == "__main__":
    main()
