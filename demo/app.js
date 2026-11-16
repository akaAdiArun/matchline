"use strict";

const byId = (id) => document.getElementById(id);
const scan = byId("invoice-scan");
const box = byId("evidence-box");
const caseButtons = Array.from(document.querySelectorAll("[data-case]"));
const fieldLabels = {
  invoice_number: "Invoice number",
  item_id: "Item ID",
  quantity: "Quantity",
  unit_price: "Unit price",
};
const decisions = {
  matched: ["Matched", "Invoice matches"],
  mismatch: ["Mismatch", "Delivery shortfall"],
  needs_review: ["Needs review", "Quantity needs review"],
};

let recordings;
let fields;
let selectedField;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function readJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return response.json();
}

function fieldLocation(field) {
  const location = field.observations[0]?.location;
  return field.value !== null && field.observations.length === 1 && location?.page === 1
    ? location
    : null;
}

function setHighlight(fieldName) {
  selectedField = fieldName;
  const field = fields[fieldName];
  const label = fieldLabels[fieldName];
  const location = fieldLocation(field);
  const observation = field.observations[0];
  box.hidden = true;
  byId("ocr-line").textContent = observation?.line_text ?? "No text recorded";
  byId("ocr-confidence").textContent = observation?.confidence != null
    ? `${observation.confidence.toFixed(1)}%`
    : "Unavailable";

  for (const button of byId("field-list").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.field === fieldName));
  }
  if (!location) {
    const readLabel = observation?.line_text;
    byId("location-status").textContent = readLabel
      ? `OCR read “${readLabel}” without locating a value.`
      : `${label} has no recorded OCR location.`;
    return;
  }
  if (!scan.complete || scan.naturalWidth === 0) {
    byId("location-status").textContent = "Loading the supplier invoice…";
    return;
  }

  const { left, top, width, height, page } = location;
  if (left < 0 || top < 0 || width <= 0 || height <= 0 ||
      left + width > scan.naturalWidth || top + height > scan.naturalHeight) {
    byId("location-status").textContent = `${label} has no usable OCR location.`;
    return;
  }
  box.style.left = `${left * 100 / scan.naturalWidth}%`;
  box.style.top = `${top * 100 / scan.naturalHeight}%`;
  box.style.width = `${width * 100 / scan.naturalWidth}%`;
  box.style.height = `${height * 100 / scan.naturalHeight}%`;
  box.hidden = false;
  byId("location-status").textContent = `${label} highlighted on page ${page}.`;
}

function showFields() {
  const buttons = Object.entries(fieldLabels).map(([name, label]) => {
    const field = fields[name];
    const missing = field.value === null;
    const value = missing ? "Unreadable" : name === "unit_price" ? `$${field.value}` : field.value;
    const button = element("button", undefined, "field");
    button.type = "button";
    button.dataset.field = name;
    button.dataset.missing = String(missing);
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-controls", "location-status");
    const icon = element("span", fieldLocation(field) ? "" : "–", "field-icon");
    icon.dataset.locatable = String(Boolean(fieldLocation(field)));
    icon.setAttribute("aria-hidden", "true");
    button.append(element("span", label, "field-label"), element("span", value, "field-value"), icon);
    button.addEventListener("click", () => setHighlight(name));
    return button;
  });
  byId("field-list").replaceChildren(...buttons);
}

function showCase(key) {
  const record = recordings.cases[key];
  const extraction = record.invoice_extraction;
  fields = extraction.fields;
  const reference = fields.invoice_number.value ?? "Invoice number unreadable";
  const [status, title] = decisions[record.status];
  for (const button of caseButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.case === key));
  }
  byId("invoice-reference").textContent = reference;
  scan.alt = `Fictional supplier invoice ${reference}`;
  scan.src = `../${extraction.source.replaceAll("\\", "/")}`;
  byId("decision").dataset.status = record.status;
  byId("decision-status").textContent = status;
  byId("decision-title").textContent = title;
  byId("decision-reason").textContent = record.reason;

  const values = record.values;
  const quantities = {
    "qty-billed": values.invoice.quantity,
    "qty-ordered": values.purchase_order.quantity,
    "qty-received": values.delivery_receipt.quantity,
  };
  for (const [id, value] of Object.entries(quantities)) {
    const output = byId(id);
    output.textContent = value ?? "Unreadable";
    output.dataset.missing = String(value === null);
  }

  showFields();
  setHighlight("quantity");
}

function count(value) {
  return `${value.correct}/${value.total}`;
}

function incorrectMatches(value) {
  return `${value.count}/${value.should_not_match}`;
}

function reviews(value) {
  return `${value.count}/${value.total} (${(100 * value.count / value.total).toFixed(1)}%)`;
}

function showBenchmark(report) {
  const ocr = report.tesseract;
  const vision = report.qwen3_vl_2b;
  const metrics = [
    ["Correct fields", "field_accuracy", count],
    ["Correct matching decisions", "decision_accuracy", count],
    ["Incorrect matches", "incorrect_matches", incorrectMatches],
    ["Sent to review", "review", reviews],
    ["Median scan-to-decision time", "median_ms", (value) => `${value.toFixed(1)} ms`],
  ];
  byId("metrics-body").replaceChildren(...metrics.map(([label, key, format]) => {
    const row = element("tr");
    const heading = element("th", label);
    heading.scope = "row";
    row.append(heading, element("td", format(ocr.metrics[key])), element("td", format(vision.metrics[key])));
    return row;
  }));

  const ocrMiss = ocr.documents.find((entry) => entry.image === "07.png");
  const missing = Object.values(ocrMiss.extraction.issues).filter((issue) => issue === "missing_label").length;
  byId("ocr-failure").textContent =
    `Invoice ${ocrMiss.expected_fields.invoice_number} should match. The parser found ${missing} missing labels and sent it to review.`;
  byId("ocr-failure-image").href = `../evaluation/images/${ocrMiss.image}`;

  const visionMiss = vision.documents.find((entry) => entry.image === "11.png");
  const rawPrice = JSON.parse(visionMiss.extraction.raw_response).unit_price;
  byId("vision-failure").textContent =
    `The model returned ${JSON.stringify(rawPrice)}. The validator expected "${visionMiss.expected_fields.unit_price}", so the invoice went to review.`;
  byId("vision-failure-image").href = `../evaluation/images/${visionMiss.image}`;
}

scan.addEventListener("load", () => setHighlight(selectedField));
scan.addEventListener("error", () => {
  box.hidden = true;
  byId("location-status").textContent = "The recorded invoice image could not be loaded.";
});

readJson("recordings.json").then((data) => {
  recordings = data;
  for (const button of caseButtons) button.addEventListener("click", () => showCase(button.dataset.case));
  showCase("short");
  byId("recording-message").hidden = true;
  byId("workspace").hidden = false;
}).catch((error) => {
  byId("recording-message").textContent = "Could not load the recordings. Start the local server from the repository root.";
  console.error(error);
});

readJson("../evaluation/results.json").then((data) => {
  showBenchmark(data);
  byId("benchmark-message").hidden = true;
  byId("benchmark-content").hidden = false;
}).catch((error) => {
  byId("benchmark-message").textContent = "Could not load the saved benchmark results.";
  console.error(error);
});
