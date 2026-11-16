"""Read invoice fields through a local Qwen3-VL llama.cpp server."""

import base64
import http.client
import json
import re
from decimal import Decimal


MODEL_ALIAS = "matchline-qwen3-vl-2b"
DEFAULT_PORT = 18973
PROMPT = (
    "Transcribe the single billed item from this invoice image. "
    "Return invoice_number (the invoice reference), item_id (the billed item code or SKU), "
    "quantity (billed units as an integer), and unit_price (price for one unit as a decimal "
    "string without a currency symbol, not the line total). Copy only visible values. "
    "Use JSON null for each missing, covered, or unreadable value. "
    "Never infer a value from totals, layout, or other fields. Return only the JSON object."
)

PROPERTIES = {
    "invoice_number": "string",
    "item_id": "string",
    "quantity": "integer",
    "unit_price": "string",
}
SCHEMA = {
    "type": "object",
    "required": list(PROPERTIES),
    "additionalProperties": False,
    "properties": {
        field: {"anyOf": [{"type": kind}, {"type": "null"}]}
        for field, kind in PROPERTIES.items()
    },
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_response(raw_text, finish_reason="stop"):
    """Keep invalid or unresolved fields null and retain the actual response."""
    values = dict.fromkeys(PROPERTIES)
    issues = {}
    try:
        if finish_reason != "stop":
            raise ValueError(f"Unfinished response: {finish_reason}")
        document = json.loads(raw_text, object_pairs_hook=_unique_object)
        if not isinstance(document, dict) or document.keys() - PROPERTIES.keys():
            raise ValueError("Expected a single invoice object with recognized fields")
    except ValueError as error:
        return {"values": values, "issues": {"response": str(error)}, "raw_response": raw_text}

    for field in PROPERTIES:
        value = document.get(field)
        if value is None:
            issues[field] = "missing_or_unreadable"
        elif field == "quantity" and type(value) is int and value >= 0:
            values[field] = value
        elif field == "unit_price" and isinstance(value, str) and re.fullmatch(
            r"[0-9]+(?:\.[0-9]{1,2})?", value
        ):
            values[field] = Decimal(value)
        elif field in ("invoice_number", "item_id") and isinstance(value, str) and re.fullmatch(
            r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", value
        ):
            values[field] = value
        else:
            issues[field] = "invalid_value"
    return {"values": values, "issues": issues, "raw_response": raw_text}


def extract_invoice(image, *, port=DEFAULT_PORT):
    """Send one PNG and a fixed prompt to a loopback server."""
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    request = {
        "model": MODEL_ALIAS,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            {"type": "text", "text": PROMPT},
        ]}],
        "response_format": {"type": "json_object", "schema": SCHEMA},
        "cache_prompt": False,
        "temperature": 0,
        "seed": 42,
        "max_tokens": 192,
        "stream": False,
    }
    server = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    try:
        server.request("POST", "/v1/chat/completions", json.dumps(request),
                       {"Content-Type": "application/json"})
        response = server.getresponse()
        body = response.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException) as error:
        raise RuntimeError(f"Local model server on port {port}: {error}") from error
    finally:
        server.close()

    if response.status != 200:
        raise RuntimeError(f"Local model server returned HTTP {response.status}: {body[:500]}")
    try:
        data = json.loads(body)
        if data["model"] != MODEL_ALIAS:
            raise ValueError(f"Unexpected model alias: {data['model']}")
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice["finish_reason"]
        if not isinstance(content, str):
            raise ValueError("Response content is not text")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise RuntimeError(f"Invalid llama.cpp response: {error}") from error
    return validate_response(content, finish_reason)
