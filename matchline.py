"""Read an invoice, order, and receipt and print the matching decision."""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from invoice_ocr import extract_invoice
from matching import match


def read_json(path):
    try:
        with path.open(encoding="utf-8") as file:
            document = json.load(file, parse_float=Decimal)
    except (OSError, ValueError, InvalidOperation) as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return document


def main():
    parser = argparse.ArgumentParser(description="Match one invoice line against an order and receipt.")
    parser.add_argument("invoice", type=Path, help="Invoice JSON file or scanned image")
    parser.add_argument("purchase_order", type=Path, help="Purchase order JSON file")
    parser.add_argument("delivery_receipt", type=Path, help="Delivery receipt JSON file")
    parser.add_argument("--invoice-image", action="store_true", help="Read the invoice with local OCR")
    args = parser.parse_args()

    extraction = None
    try:
        order = read_json(args.purchase_order)
        receipt = read_json(args.delivery_receipt)
        if args.invoice_image:
            extraction = extract_invoice(args.invoice)
            invoice = {name: field["value"] for name, field in extraction["fields"].items()}
        else:
            invoice = read_json(args.invoice)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    decision = match(invoice, order, receipt)
    if extraction is not None:
        if invoice["invoice_number"] is None:
            reason = "Invoice number is missing or unreadable."
            if decision["status"] == "needs_review":
                reason += " " + decision["reason"]
            decision.update(status="needs_review", reason=reason)
        decision["invoice_extraction"] = extraction

    print(json.dumps(decision, indent=2, default=str))


if __name__ == "__main__":
    main()
