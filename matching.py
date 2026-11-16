"""Three-way matching rules for one item in three structured documents."""

from decimal import Decimal


def match(invoice, purchase_order, delivery_receipt):
    """Return a decision, its reason, and the values read from each document."""
    values = {}
    review_reasons = []
    documents = (
        ("invoice", "Invoice", invoice),
        ("purchase_order", "Purchase order", purchase_order),
        ("delivery_receipt", "Delivery receipt", delivery_receipt),
    )

    for source, label, document in documents:
        item_id = document.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            review_reasons.append(f"{label} item ID is missing or unreadable.")
            item_id = None

        quantity = document.get("quantity")
        if type(quantity) is not int or quantity < 0:
            review_reasons.append(
                f"{label} quantity is missing or invalid. Expected a non-negative whole number."
            )
            quantity = None

        values[source] = {"item_id": item_id, "quantity": quantity}
        if source != "delivery_receipt":
            price = document.get("unit_price")
            if type(price) is int:
                price = Decimal(price)
            if not isinstance(price, Decimal) or not price.is_finite() or price < 0:
                review_reasons.append(
                    f"{label} unit price is missing or invalid. Expected a non-negative number."
                )
                price = None
            values[source]["unit_price"] = price

    if review_reasons:
        return {"status": "needs_review", "reason": " ".join(review_reasons), "values": values}

    if len({item["item_id"] for item in values.values()}) != 1:
        return {
            "status": "mismatch",
            "reason": "The invoice, purchase order, and delivery receipt refer to different items.",
            "values": values,
        }

    billed = values["invoice"]["quantity"]
    ordered = values["purchase_order"]["quantity"]
    received = values["delivery_receipt"]["quantity"]
    invoice_price = values["invoice"]["unit_price"]
    order_price = values["purchase_order"]["unit_price"]
    differences = []

    if billed != ordered:
        differences.append(f"Invoice quantity {billed} differs from purchase order quantity {ordered}.")
    if billed > received:
        differences.append(
            f"{billed - received} units billed but not received ({billed} billed, {received} received)."
        )
    elif billed < received:
        differences.append(
            f"{received - billed} units received but not billed ({received} received, {billed} billed)."
        )
    if invoice_price != order_price:
        differences.append(
            f"Invoice unit price {invoice_price} differs from purchase order unit price {order_price}."
        )

    if differences:
        return {"status": "mismatch", "reason": " ".join(differences), "values": values}

    return {"status": "matched", "reason": "Item IDs, quantities, and unit prices agree.", "values": values}
