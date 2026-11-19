# SKILL: KYC Document Processing Pipeline

## Overview

An end-to-end multi-agent pipeline that accepts scanned images or PDFs of Indian identity documents, identifies the document type, extracts structured fields, validates the data, applies mandatory masking, and returns a clean JSON response via an API endpoint.

Supported document types: **Aadhaar Card, PAN Card, Voter ID, Driving Licence, Passport**

---

## Architecture

The pipeline follows a sequential agent chain with one parallel stage, exactly as shown in the reference diagram:

```
Orchestrator → Ingestion → [PDF Text Agent | OCR Agent]
             → Classifier → Extractor (LLM)
             → [Validator ‖ Masker] (parallel)
             → Aggregator → JSON response
```

### Agent Responsibilities

| Agent | Role | Key Details |
|---|---|---|
| **Orchestrator** | Entry point — receives document, routes to Ingestion, collects final result | Exposes the API endpoint; owns request/response lifecycle |
| **Ingestion** | Detects file format and decides processing path | PDF-with-text → PDF Text Agent; image or scanned PDF → OCR Agent |
| **PDF Text Agent** | Extracts raw text from digital PDFs | Uses `pdfplumber` for direct text extraction |
| **OCR Agent** | Processes images and scanned PDFs | Deskews, denoises, then runs Tesseract or Vision API |
| **Classifier** | Identifies document type + confidence | Returns doc type enum or rejects unknowns with `error_json` |
| **Extractor (LLM)** | Extracts structured fields using a schema-guided prompt | Outputs raw field JSON; one schema per document type |
| **Validator** | Validates extracted fields (runs in parallel with Masker) | PAN regex, Aadhaar Luhn, MRZ checksum, DL expiry; outputs `warnings[]` |
| **Masker** | Applies mandatory masking rules (runs in parallel with Validator) | Aadhaar `XXXX XXXX NNNN` enforced before any serialization |
| **Aggregator** | Merges validator warnings + masked fields into final JSON | Outputs `doc_type`, `fields`, `confidence`, `warnings`, `masked`, `field_level_scores` |

---

## Expected Output Structure

```json
{
  "document_type": "aadhaar",
  "confidence": 0.97,
  "fields": {
    "name": "Priya Sharma",
    "dob": "1990-04-12",
    "gender": "F",
    "address": "12 MG Road, Bengaluru, Karnataka 560001",
    "aadhaar_number": "XXXX XXXX 3456"
  },
  "masked": true,
  "field_level_scores": {
    "name": 0.99,
    "dob": 0.98,
    "aadhaar_number": 0.95,
    "address": 0.81
  },
  "extraction_warnings": ["low_scan_quality_on_address_field"]
}
```

On rejection (unknown document type):
```json
{
  "document_type": null,
  "confidence": 0.0,
  "fields": {},
  "masked": false,
  "extraction_warnings": [],
  "error": "unsupported_document_type",
  "error_detail": "Document could not be classified as one of the five supported types."
}
```

---

## Document Schemas

### Aadhaar Card
| Field | Validation | Masking |
|---|---|---|
| `name` | Non-empty string | None |
| `dob` | ISO 8601 date (`YYYY-MM-DD`) | None |
| `gender` | `M` / `F` / `O` | None |
| `address` | Non-empty string | None |
| `aadhaar_number` | 12-digit Luhn-valid number | **First 8 digits → `XXXX XXXX`** (mandatory, enforced before any serialization or logging) |

### PAN Card
| Field | Validation |
|---|---|
| `name` | Non-empty string |
| `fathers_name` | Non-empty string |
| `dob` | ISO 8601 date |
| `pan_number` | Regex: `^[A-Z]{5}[0-9]{4}[A-Z]$` |

### Voter ID
| Field | Notes |
|---|---|
| `name` | — |
| `relative_name` | Father's or Husband's name |
| `dob` | ISO 8601 date |
| `voter_id_number` | — |
| `address` | State-variant handling required |
| `constituency` | — |

### Driving Licence
| Field | Validation |
|---|---|
| `name` | — |
| `dob` | ISO 8601 date |
| `dl_number` | — |
| `valid_from` | ISO 8601 date |
| `valid_until` | **Must be in the future** — emit `warning: dl_expired` if not |
| `vehicle_classes` | Array of strings, e.g. `["LMV", "MCWG"]` |
| `address` | — |

### Passport
| Field | Validation |
|---|---|
| `name` | Must match MRZ surname + given name |
| `dob` | ISO 8601 date; must match MRZ field |
| `passport_number` | Must match MRZ field |
| `nationality` | 3-letter ISO country code |
| `expiry_date` | ISO 8601 date; must match MRZ field |
| `mrz_line` | Full MRZ string; checksum validated against biographical fields |

---

## Ingestion Agent — Format Detection

```
if file is PDF:
    attempt pdfplumber text extraction
    if extracted_text.strip() != "":
        route → PDF Text Agent
    else:
        route → OCR Agent   # scanned / image-only PDF
else:
    route → OCR Agent       # PNG, JPEG, TIFF, etc.
```

---

## OCR Agent — Image Pre-processing

Run in order before OCR:

1. **Deskew** — detect and correct rotation (OpenCV Hough transform or `deskew` library)
2. **Denoise** — apply median blur or bilateral filter for low-resolution scans
3. **Binarize** — Otsu threshold for clean black-and-white output
4. **Upscale** — if DPI < 150, upscale 2× with `PIL` / `cv2.resize` before OCR
5. **OCR** — Tesseract (`lang=eng+hin` for Aadhaar; `lang=eng` otherwise), or Vision API as fallback

If Tesseract confidence (mean word confidence) < 60, flag `warning: low_scan_quality_on_<field>` for affected fields.

---

## Classifier Agent

Input: raw text string
Output: `{ "document_type": <enum|null>, "confidence": <float> }`

Classification strategy (rule-based first, LLM fallback):

```
1. Keyword scan:
   "UNIQUE IDENTIFICATION" or "आधार"  → aadhaar
   "INCOME TAX DEPARTMENT" + PAN regex → pan
   "ELECTION COMMISSION"               → voter_id
   "DRIVING LICENCE"                   → driving_licence
   "REPUBLIC OF INDIA" + "PASSPORT"    → passport

2. If keyword confidence < 0.7:
   Call LLM classifier with few-shot examples

3. If max confidence < 0.5:
   Reject → error_json ("unsupported_document_type")
```

---

## Extractor Agent (LLM)

Uses a **schema-guided system prompt** per document type. The prompt must:

- List every required field by name
- Specify the expected format (e.g., `dob` → `YYYY-MM-DD`)
- Instruct the model to return **only valid JSON**, no preamble
- Instruct the model to emit `null` for fields that cannot be read (never hallucinate)
- Include a `field_confidence` block (0.0–1.0 per field)

Example system prompt fragment for Aadhaar:
```
You are an OCR post-processor. Extract the following fields from the raw text of an Aadhaar card.
Return ONLY a JSON object with these keys: name, dob (YYYY-MM-DD), gender (M/F/O),
address, aadhaar_number (12 digits, no spaces), field_confidence (object, 0.0-1.0 per field).
If a field is unreadable, set it to null. Do not invent values.
```

---

## Validator Agent (runs in parallel with Masker)

Validations by document type:

```python
# PAN
assert re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan_number)

# Aadhaar — Luhn check
def luhn_valid(number: str) -> bool: ...

# Driving Licence — expiry
assert datetime.strptime(valid_until, "%Y-%m-%d").date() > date.today(), "dl_expired"

# Passport — MRZ checksum
def mrz_check(mrz_line: str, fields: dict) -> list[str]: ...
# Validates checksum digits for passport_number, dob, expiry_date
# Also validates name match between MRZ and biographical field
```

Output: `warnings: list[str]` — e.g., `["dl_expired", "mrz_dob_mismatch", "pan_format_invalid"]`

---

## Masker Agent (runs in parallel with Validator)

**Aadhaar masking is mandatory and non-negotiable.**

```python
def mask_aadhaar(number: str) -> str:
    """
    Input:  "1234 5678 9012"  or  "123456789012"
    Output: "XXXX XXXX 9012"
    Rule:   First 8 digits → 'X'; last 4 digits preserved; format with spaces.
    """
    digits = number.replace(" ", "")
    assert len(digits) == 12
    return f"XXXX XXXX {digits[-4:]}"
```

Critical enforcement rules:
- The unmasked Aadhaar number **must never appear** in any API response body, log line, database record, or error message
- Masking is applied by the Masker agent **before** the Aggregator serializes the response
- The Extractor's raw output (which may contain the full number) is held only in memory and discarded after the parallel stage

---

## Aggregator → Final JSON

Merges outputs of Validator and Masker:

```python
response = {
    "document_type": classifier_result["document_type"],
    "confidence": classifier_result["confidence"],
    "fields": masker_result["masked_fields"],       # masked fields only
    "masked": masker_result["masking_applied"],
    "field_level_scores": extractor_result["field_confidence"],
    "extraction_warnings": validator_result["warnings"]
}
```

---

## API Endpoint

```
POST /api/v1/kyc/process
Content-Type: multipart/form-data

file: <binary> (PDF, PNG, JPEG, TIFF)
```

Response:
```
HTTP 200 — success (document processed, may include warnings)
HTTP 422 — unsupported document type (error_json returned in body)
HTTP 400 — file unreadable / corrupt
HTTP 500 — pipeline internal error
```

---

## Implementation Stack

| Component | Recommended Library |
|---|---|
| API server | FastAPI + Uvicorn |
| PDF text extraction | `pdfplumber` |
| Image pre-processing | `opencv-python`, `Pillow` |
| OCR | `pytesseract` (Tesseract 5), Google Vision API (fallback) |
| LLM calls (Extractor, Classifier fallback) | Anthropic `claude-sonnet-4` via `anthropic` SDK |
| MRZ parsing | `mrz` or `passporteye` |
| Luhn validation | Pure Python (no external dep) |
| Async parallel execution | `asyncio.gather()` for Validator + Masker stage |

---

## Real-World Scan Handling

| Issue | Mitigation |
|---|---|
| Skewed scan | Deskew in OCR pre-processing (Hough transform) |
| Low resolution | Upscale if DPI < 150; flag `low_scan_quality` warning |
| Partial occlusion | Set field to `null`; emit `field_unreadable_<field>` warning |
| Hindi text (Aadhaar) | Tesseract `lang=eng+hin`; extract English fields from English region |
| State-variant Voter IDs | Classifier uses regional keyword variants; Extractor handles flexible layouts |
| Glossy / reflective surface | Denoise + binarize in pre-processing |

---

## Security & Compliance

- Aadhaar numbers are **never logged** at any verbosity level — use a log filter that redacts 12-digit numeric sequences
- Uploaded files are processed in memory or a temporary directory; temp files are deleted immediately after processing
- API responses are served over HTTPS only
- No extracted PII is persisted beyond the request lifecycle unless the caller explicitly stores the JSON response

---

## Testing Requirements

Submit a test set covering at least:

| Test case | Document type | Condition |
|---|---|---|
| 1 | Aadhaar | Clean scan — verify masking applied, all fields extracted |
| 2 | PAN or Passport | Clean scan — verify format validation passes |
| 3 | Any supported type | Degraded scan (skewed / low-res) — verify warnings emitted, partial extraction |
| 4 | Unsupported document | e.g., utility bill — verify graceful rejection with error JSON |
| 5 | Driving Licence (expired) | Verify `dl_expired` warning in output |

---

## Common Warnings Reference

| Warning string | Meaning |
|---|---|
| `low_scan_quality_on_<field>` | OCR confidence below threshold for that field |
| `field_unreadable_<field>` | Field could not be extracted; set to `null` |
| `pan_format_invalid` | PAN does not match `^[A-Z]{5}[0-9]{4}[A-Z]$` |
| `aadhaar_luhn_failed` | Aadhaar number fails Luhn checksum |
| `dl_expired` | Driving Licence `valid_until` is in the past |
| `mrz_checksum_failed` | MRZ checksum digit does not validate |
| `mrz_dob_mismatch` | DOB in MRZ does not match biographical DOB field |
| `mrz_name_mismatch` | Name in MRZ does not match name field |