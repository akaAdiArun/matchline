# Matchline

Matchline is an AI invoice auditor that shows its work. It reads a supplier invoice, compares it with the purchase order and delivery receipt, and shows the evidence behind its decision. If a supplier bills for 100 units and the warehouse received 60, it flags the 40-unit discrepancy and shows where the numbers came from. When a blurry invoice leaves a required field unreadable, it asks for human review. Matchline never approves or moves money.

This is a flagship portfolio project for Applied AI Engineering roles. It should show where a model helps, where it fails, and how the system handles those failures. Keep document extraction separate from the matching engine so competing extraction methods produce inputs for the same decision rules.

## Roadmap

1. **Matching engine.** Build and test the rules using fictional structured data. Compare one item across an invoice, purchase order, and delivery receipt. Return the decision, reason, and input values keyed by document.
2. **Document extraction.** Read invoices with OCR and simple parsing. Preserve source evidence and send unreadable fields to human review.
3. **AI evaluation.** Compare the OCR baseline and a vision-language model on the same held-out documents. Measure extraction accuracy, how often bad invoices are incorrectly marked as matched, the human review rate, and latency. Publish actual results and instructions to reproduce them.
4. **Demo.** Build a small interface with three examples covering a clean match, a discrepancy, and an unreadable invoice. Let users click a flagged value to see its source.

Milestone 1 uses fictional JSON to stand in for extracted values. See [matching.py](../matching.py) for the decision rules and [README.md](../README.md) for commands and the input format.
