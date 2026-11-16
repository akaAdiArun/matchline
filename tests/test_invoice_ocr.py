import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from invoice_ocr import OCR_EXE_ENV, parse_invoice_tsv


ROOT = Path(__file__).resolve().parents[1]
TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def ocr_rows(*lines):
    rows = [TSV_HEADER]
    for line_number, tokens in enumerate(lines, start=1):
        for word_number, (text, confidence) in enumerate(tokens, start=1):
            word = (5, 1, 1, 1, line_number, word_number, word_number * 100,
                    line_number * 50, len(text) * 5, 20, confidence, text)
            rows.append("\t".join(map(str, word)))
    return "\n".join(rows)


class InvoiceParsingTests(unittest.TestCase):
    def test_parses_value_joined_to_label_and_keeps_its_word_box(self):
        fields = parse_invoice_tsv(ocr_rows([("Quantity:37", 94)]))
        quantity = fields["quantity"]
        self.assertEqual(quantity["value"], 37)
        self.assertIsNone(quantity["issue"])
        self.assertEqual(quantity["observations"][0]["raw_text"], "37")
        self.assertEqual(quantity["observations"][0]["location"],
                         {"page": 1, "left": 100, "top": 50, "width": 55, "height": 20})

    def test_low_confidence_quantity_keeps_evidence_without_a_value(self):
        fields = parse_invoice_tsv(ocr_rows([("Quantity:", 96), ("37", 31)]))
        quantity = fields["quantity"]
        self.assertIsNone(quantity["value"])
        self.assertEqual(quantity["issue"], "low_confidence")
        self.assertEqual(quantity["observations"][0]["raw_text"], "37")
        self.assertEqual(quantity["observations"][0]["confidence"], 31)
        self.assertEqual(quantity["observations"][0]["location"]["left"], 200)

    def test_duplicate_quantity_lines_keep_both_candidates_for_review(self):
        fields = parse_invoice_tsv(ocr_rows(
            [("Quantity:", 96), ("37", 98)],
            [("Quantity:", 96), ("41", 98)],
        ))
        quantity = fields["quantity"]
        self.assertIsNone(quantity["value"])
        self.assertEqual(quantity["issue"], "multiple_labels")
        self.assertEqual([entry["raw_text"] for entry in quantity["observations"]], ["37", "41"])


@unittest.skipUnless(shutil.which(os.environ.get(OCR_EXE_ENV, "tesseract")), "Tesseract is unavailable")
class ScannedInvoiceTests(unittest.TestCase):
    def run_invoice(self, scan, receipt="receipt.json"):
        result = subprocess.run(
            [
                sys.executable, "-m", "matchline", "--invoice-image",
                f"examples/scans/{scan}", "examples/purchase-order.json", f"examples/{receipt}",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_clean_scan_has_values_and_page_locations(self):
        result = self.run_invoice("clean.png")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["invoice_extraction"]["source"], str(Path("examples/scans/clean.png")))
        fields = result["invoice_extraction"]["fields"]
        expected = {
            "invoice_number": ("ML-1048", "ML-1048"),
            "item_id": ("FILTER-01", "FILTER-01"),
            "quantity": (100, "100"),
            "unit_price": ("12.50", "$12.50"),
        }
        for name, (value, raw_text) in expected.items():
            with self.subTest(field=name):
                self.assertEqual(fields[name]["value"], value)
                self.assertIsNone(fields[name]["issue"])
                observation, = fields[name]["observations"]
                self.assertEqual(observation["raw_text"], raw_text)
                box = observation["location"]
                self.assertEqual(box["page"], 1)
                self.assertGreater(box["left"], 0)
                self.assertGreater(box["top"], 0)
                self.assertGreater(box["width"], 0)
                self.assertGreater(box["height"], 0)

    def test_short_delivery_uses_scanned_quantity_and_reports_shortfall(self):
        result = self.run_invoice("short-delivery.png", "receipt-short.json")
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("40 units billed but not received", result["reason"])
        self.assertEqual(result["invoice_extraction"]["fields"]["invoice_number"]["value"], "ML-2064")
        self.assertEqual(result["values"]["invoice"]["quantity"], 100)
        self.assertEqual(result["values"]["delivery_receipt"]["quantity"], 60)

    def test_covered_scan_preserves_both_unresolved_fields(self):
        result = self.run_invoice("unreadable-quantity.png")
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("Invoice quantity", result["reason"])
        self.assertIsNone(result["values"]["invoice"]["quantity"])
        self.assertEqual(result["values"]["purchase_order"]["quantity"], 100)
        fields = result["invoice_extraction"]["fields"]
        self.assertEqual(fields["invoice_number"]["value"], "ML-3192")
        self.assertEqual(fields["unit_price"]["value"], "12.50")
        self.assertIsNone(fields["item_id"]["value"])
        self.assertEqual(fields["item_id"]["issue"], "low_confidence")
        self.assertIsNone(fields["quantity"]["value"])
        self.assertIsNotNone(fields["quantity"]["issue"])

    def test_quantity_alone_unreadable_requires_review(self):
        result = self.run_invoice("quantity-only-obscured.png")
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(result["reason"].startswith("Invoice quantity"))
        fields = result["invoice_extraction"]["fields"]
        self.assertEqual(
            {name: field["value"] for name, field in fields.items()},
            {"invoice_number": "ML-1048", "item_id": "FILTER-01", "quantity": None, "unit_price": "12.50"},
        )
        self.assertEqual(fields["quantity"]["issue"], "missing_value")
        self.assertEqual(result["values"]["purchase_order"]["quantity"], 100)


if __name__ == "__main__":
    unittest.main()
