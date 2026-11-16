import unittest
from decimal import Decimal

from matching import match
from vision_invoice import validate_response


class VisionResponseTests(unittest.TestCase):
    def test_accepts_visible_fields_and_keeps_unreadable_quantity_null(self):
        result = validate_response(
            '{"invoice_number":"VX-732","item_id":"PART-642","quantity":null,"unit_price":"6.40"}'
        )
        self.assertEqual(result["values"], {
            "invoice_number": "VX-732", "item_id": "PART-642",
            "quantity": None, "unit_price": Decimal("6.40"),
        })
        order = {"item_id": "PART-642", "quantity": 100, "unit_price": Decimal("6.40")}
        receipt = {"item_id": "PART-642", "quantity": 100}
        self.assertEqual(
            match(result["values"], order, receipt, require_invoice_number=True)["status"],
            "needs_review",
        )

    def test_invalid_types_and_values_are_not_coerced(self):
        for quantity in ("true", '"12"', "-1", "1.5"):
            with self.subTest(quantity=quantity):
                raw = (
                    '{"invoice_number":" N/A ","item_id":"PART-642",'
                    + '"quantity":' + quantity + ',"unit_price":"6.40 or 8.40"}'
                )
                result = validate_response(raw)
                self.assertEqual(result["values"], {
                    "invoice_number": None, "item_id": "PART-642",
                    "quantity": None, "unit_price": None,
                })
                self.assertEqual(set(result["issues"]), {"invoice_number", "quantity", "unit_price"})

    def test_duplicate_or_truncated_responses_require_review(self):
        for raw, finish_reason in (
            ('{"quantity":12,"quantity":21}', "stop"),
            ('{"quantity":21}', "length"),
        ):
            with self.subTest(finish_reason=finish_reason):
                result = validate_response(raw, finish_reason)
                self.assertTrue(all(value is None for value in result["values"].values()))
                self.assertIn("response", result["issues"])
                self.assertEqual(result["raw_response"], raw)

    def test_shared_scan_rule_requires_invoice_number(self):
        invoice = {"item_id": "PART-642", "quantity": 32, "unit_price": Decimal("6.40")}
        receipt = {"item_id": "PART-642", "quantity": 32}
        decision = match(invoice, invoice, receipt, require_invoice_number=True)
        self.assertEqual(decision["status"], "needs_review")
        self.assertEqual(decision["reason"], "Invoice number is missing or unreadable.")


if __name__ == "__main__":
    unittest.main()
