"""Read one invoice image with Tesseract and parse labeled fields."""

import csv
import io
import os
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal


OCR_EXE_ENV = "MATCHLINE_TESSERACT"
MIN_CONFIDENCE = 80.0
ID_FORMAT = r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*"
FIELDS = {
    "invoice_number": ("Invoice number", ID_FORMAT, str),
    "item_id": ("Item ID", ID_FORMAT, str),
    "quantity": ("Quantity", r"[0-9]+", int),
    "unit_price": ("Unit price", r"\$?\s*[0-9]+(?:\.[0-9]{1,2})?", Decimal),
}


@dataclass(frozen=True)
class Word:
    text: str
    confidence: float
    page: int
    left: int
    top: int
    width: int
    height: int


def _location(words):
    left = min(word.left for word in words)
    top = min(word.top for word in words)
    return {
        "page": words[0].page,
        "left": left,
        "top": top,
        "width": max(word.left + word.width for word in words) - left,
        "height": max(word.top + word.height for word in words) - top,
    }


def _observation(words, line_text, value_start):
    # The line joins OCR words with one space. Use the character offset to
    # find the source words even when Tesseract joins a label and its value.
    value_words = []
    end = 0
    for word in words:
        end += len(word.text)
        if end > value_start:
            value_words.append(word)
        end += 1

    return {
        "raw_text": line_text[value_start:] or None,
        "location": _location(value_words) if value_words else None,
        "line_text": line_text,
        "line_location": _location(words),
        "confidence": min((word.confidence for word in value_words), default=None),
    }


def parse_invoice_tsv(tsv):
    """Return normalized fields and their OCR observations."""
    rows = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    if not rows.fieldnames or "text" not in rows.fieldnames:
        raise ValueError("Tesseract did not return word TSV output.")

    lines = {}
    for row in rows:
        if row["level"] != "5" or not row["text"].strip():
            continue
        line = tuple(int(row[key]) for key in ("page_num", "block_num", "par_num", "line_num"))
        word = Word(
            row["text"].strip(), float(row["conf"]), line[0],
            int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"]),
        )
        lines.setdefault(line, []).append(word)

    text_lines = [(" ".join(word.text for word in words), words) for words in lines.values()]
    fields = {}
    for name, (label, pattern, convert) in FIELDS.items():
        observations = []
        label_pattern = re.compile(rf"{re.escape(label)}\s*:\s*", re.IGNORECASE)
        for line_text, words in text_lines:
            label_match = label_pattern.match(line_text)
            if label_match:
                observations.append(_observation(words, line_text, label_match.end()))

        value = None
        if not observations:
            issue = "missing_label"
        elif len(observations) > 1:
            issue = "multiple_labels"
        else:
            observation = observations[0]
            raw_text = observation["raw_text"]
            if raw_text is None:
                issue = "missing_value"
            elif not re.fullmatch(pattern, raw_text):
                issue = "invalid_format"
            elif observation["confidence"] < MIN_CONFIDENCE:
                issue = "low_confidence"
            else:
                value = convert(raw_text.removeprefix("$").strip())
                issue = None
        fields[name] = {"value": value, "issue": issue, "observations": observations}

    return fields


def extract_invoice(image):
    """Run local English OCR and return invoice values with source evidence."""
    executable = os.environ.get(OCR_EXE_ENV, "tesseract")
    command = [executable, str(image.resolve()), "stdout", "-l", "eng", "--psm", "6", "tsv"]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
    except FileNotFoundError as error:
        raise ValueError(
            f"Tesseract executable not found. Put it on PATH or set {OCR_EXE_ENV}."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise ValueError("Tesseract did not finish within 30 seconds.") from error
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Tesseract failed (exit {error.returncode}): {error.stderr.strip()}"
        ) from error

    return {"source": str(image), "fields": parse_invoice_tsv(result.stdout)}
