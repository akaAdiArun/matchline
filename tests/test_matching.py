import json
import unittest
from decimal import Decimal
from pathlib import Path

from matching import match


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name):
    with (EXAMPLES / name).open(encoding="utf-8") as file:
        return json.load(file, parse_float=Decimal)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.invoice = load_example("invoice.json")
        self.order = load_example("purchase-order.json")
        self.receipt = load_example("receipt.json")

    def test_agreeing_documents_match(self):
        result = match(self.invoice, self.order, self.receipt)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["values"]["invoice"], self.invoice)
        self.assertEqual(result["values"]["purchase_order"], self.order)
        self.assertEqual(result["values"]["delivery_receipt"], self.receipt)

    def test_short_receipt_reports_40_units_billed_but_not_received(self):
        receipt = load_example("receipt-short.json")
        result = match(self.invoice, self.order, receipt)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("40 units billed but not received", result["reason"])
        self.assertEqual(result["values"]["delivery_receipt"]["quantity"], 60)
        self.assertEqual(match(self.invoice, self.order, {**receipt, "quantity": 100})["status"], "matched")

    def test_price_mismatch_shows_both_prices(self):
        invoice = load_example("invoice-price-mismatch.json")
        result = match(invoice, self.order, self.receipt)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("Invoice unit price 13.25 differs from purchase order unit price 12.50", result["reason"])
        self.assertEqual(result["values"]["invoice"]["unit_price"], Decimal("13.25"))
        self.assertEqual(result["values"]["purchase_order"]["unit_price"], Decimal("12.50"))

    def test_unreadable_invoice_quantity_requires_review(self):
        invoice = load_example("invoice-unreadable.json")
        result = match(invoice, self.order, self.receipt)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("Invoice quantity", result["reason"])
        self.assertIsNone(result["values"]["invoice"]["quantity"])

    def test_omitted_invoice_quantity_requires_review(self):
        del self.invoice["quantity"]
        result = match(self.invoice, self.order, self.receipt)
        self.assertEqual(result["status"], "needs_review")
        self.assertIsNone(result["values"]["invoice"]["quantity"])

    def test_explicit_zero_quantities_can_match(self):
        for document in (self.invoice, self.order, self.receipt):
            document["quantity"] = 0
        self.assertEqual(match(self.invoice, self.order, self.receipt)["status"], "matched")

    def test_different_item_id_is_a_mismatch_even_when_numbers_agree(self):
        self.receipt["item_id"] = "FILTER-02"
        result = match(self.invoice, self.order, self.receipt)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("different items", result["reason"])


if __name__ == "__main__":
    unittest.main()
