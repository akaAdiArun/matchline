# Matchline

Matchline compares one item across a supplier invoice, a purchase order, and a delivery receipt. It reports its decision, the reason, and the values read from each document. See [the project roadmap](docs/PROJECT.md) for the full invoice auditor.

Start with [matching.py](matching.py). It contains the decision rules. [matchline.py](matchline.py) reads the input files and prints the result as JSON.

## Run the examples

Run these commands from the repository root with Python 3. No third-party packages are required.

```sh
python -m matchline examples/invoice.json examples/purchase-order.json examples/receipt.json
python -m matchline examples/invoice.json examples/purchase-order.json examples/receipt-short.json
python -m matchline examples/invoice-price-mismatch.json examples/purchase-order.json examples/receipt.json
python -m matchline examples/invoice-unreadable.json examples/purchase-order.json examples/receipt.json
```

| Command | Expected status | Evidence |
| --- | --- | --- |
| First | `matched` | All three documents show 100 units, and the invoice and order both show a unit price of 12.50. |
| Second | `mismatch` | 100 billed and 60 received, leaving 40 units billed but not received. |
| Third | `mismatch` | Invoice unit price 13.25 and purchase order unit price 12.50. |
| Fourth | `needs_review` | The invoice quantity is `null`. |

To try the receipt change, run the second command, then change its last argument to `examples/receipt.json` and run it again. The only difference between the two receipt files is their quantity, which goes from 60 to 100. The result changes from `mismatch` to `matched`.

## Run the tests

```sh
python -m unittest discover -s tests -v
```

## Input and decision rules

Pass three UTF-8 JSON objects as separate files in invoice, purchase order, delivery receipt order. Each object represents one line item and has an `item_id` (a nonblank string) and a `quantity` (a non-negative JSON integer). The invoice and purchase order also have a `unit_price` (a finite, non-negative JSON number). The two prices are assumed to be in the same currency. The program compares prices exactly and prints them as decimal strings.

All item IDs and quantities must agree, and the invoice unit price must equal the purchase order unit price. A missing, null, or invalid required value takes precedence and returns `needs_review`. The result keeps that value as `null` and identifies the affected field. The CLI exits successfully for any of the three decisions. A file it cannot read, invalid JSON, or a top-level value other than an object is a command error.
