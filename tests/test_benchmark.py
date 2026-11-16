import unittest
from collections import Counter
from decimal import Decimal

from benchmark import EVALUATION, load_cases, score


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_held_out_assets_and_independent_decision_labels(self):
        cases = load_cases(EVALUATION)
        self.assertEqual(
            Counter(case["expected_status"] for case in cases),
            {"matched": 5, "mismatch": 5, "needs_review": 2},
        )

    def test_scores_incorrect_matches_against_nonmatching_cases(self):
        invoice = {"invoice_number": "QA-781", "item_id": "PART-592",
                   "quantity": 10, "unit_price": Decimal("11.49")}
        rows = [
            {
                "expected_fields": invoice, "extraction": {"values": invoice},
                "expected_status": "matched", "status": "matched", "latency_ms": 100.0,
            },
            {
                "expected_fields": {**invoice, "quantity": None},
                "extraction": {"values": invoice},
                "expected_status": "needs_review", "status": "matched", "latency_ms": 300.0,
            },
            {
                "expected_fields": invoice, "extraction": {"values": {**invoice, "unit_price": None}},
                "expected_status": "mismatch", "status": "needs_review", "latency_ms": 200.0,
            },
        ]
        metrics = score(rows)
        self.assertEqual(metrics["field_accuracy"], {"correct": 10, "total": 12})
        self.assertEqual(metrics["readable_fields"], {"correct": 10, "total": 11})
        self.assertEqual(metrics["unreadable_fields"], {"correct": 0, "total": 1})
        self.assertEqual(metrics["incorrect_matches"], {"count": 1, "should_not_match": 2})
        self.assertEqual(metrics["review"], {"count": 1, "total": 3})
        self.assertEqual(metrics["decision_accuracy"], {"correct": 1, "total": 3})
        self.assertEqual(metrics["median_ms"], 200.0)


if __name__ == "__main__":
    unittest.main()
