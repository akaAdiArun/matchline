"""Read three JSON documents and print the matching decision."""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from matching import match


def main():
    parser = argparse.ArgumentParser(description="Match one invoice line against an order and receipt.")
    parser.add_argument("invoice", type=Path, help="Invoice JSON file")
    parser.add_argument("purchase_order", type=Path, help="Purchase order JSON file")
    parser.add_argument("delivery_receipt", type=Path, help="Delivery receipt JSON file")
    args = parser.parse_args()

    documents = []
    for path in (args.invoice, args.purchase_order, args.delivery_receipt):
        try:
            with path.open(encoding="utf-8") as file:
                document = json.load(file, parse_float=Decimal)
        except (OSError, ValueError, InvalidOperation) as error:
            parser.error(f"{path}: {error}")
        if not isinstance(document, dict):
            parser.error(f"{path}: expected a JSON object")
        documents.append(document)

    print(json.dumps(match(*documents), indent=2, default=str))


if __name__ == "__main__":
    main()
