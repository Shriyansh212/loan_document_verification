# Document Verification Pipeline — LLM Extraction

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Groq Llama 3.3](https://img.shields.io/badge/LLM-Groq%20Llama%203.3%2070B-F55036.svg)](https://console.groq.com)
[![Tesseract OCR](https://img.shields.io/badge/OCR-Tesseract%205.0-blue.svg)](https://github.com/tesseract-ocr/tesseract)
[![SQLite Audit](https://img.shields.io/badge/Database-SQLite%20(WAL)-003B57.svg?logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An end-to-end, production-style identity document verification pipeline that turns messy scanned Indian identity documents into validated structured data, with automated policy routing to **PASS**, **FAIL**, or **MANUAL REVIEW**, supported by a modern interactive web interface and SQL-backed stage audit logs.

---

## 🎯 Key Capabilities & Resume Highlights

- **Multi-Stage Production Pipeline**: Sequential and parallel agent workflow (`OCR` → `LLM Extraction` → `Validation & PII Masking` → `Automated Routing`) turning low-resolution scans into structured JSON.
- **Groq Llama 3.3 Prompt-Based Extraction**: Schema-guided prompts instruct `llama-3.3-70b-versatile` to parse noisy OCR text into strictly formatted fields with field-level confidence scores.
- **Automated Routing Engine**: Comprehensive Python validation evaluating missing fields, cross-field discrepancies, Luhn/MRZ check digits, and routing files into **PASS**, **FAIL**, or **MANUAL REVIEW**.
- **SQL-Backed Result Storage & Audit Trail**: SQLite database with WAL mode logging microsecond execution times, stage inputs, and stage outputs for full regulatory compliance and debugging traceability.
- **Mandatory Aadhaar PII Masking**: First 8 digits (`XXXX XXXX 1234`) redacted strictly before any response serialization or storage.
- **Interactive Web Studio**: Sleek glassmorphism UI featuring live stage-by-stage pipeline visualization, 1-click test presets, document preview, and searchable historical audit table.

---

## 🏗️ Architecture

```
                                  [ Upload / Ingestion ]
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
             [ PDF Text Agent ]                            [ OCR Agent ]
             Digital Selectable Text                  Deskew ➔ Denoise ➔ Upscale ➔ Tesseract
                       │                                           │
                       └─────────────────────┬─────────────────────┘
                                             ▼
                                  [ Document Classifier ]
                                Fuzzy Keyword + Groq Llama
                                             │
                                             ▼
                                 [ LLM Extractor Agent ]
                                Groq Llama 3.3 70B Versatile
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼ (Parallel Execution)                      ▼ (Parallel Execution)
              [ Validator Agent ]                          [ Masker Agent ]
        • PAN Regex Check                           • Mandatory Aadhaar Masking
        • Aadhaar Luhn Checksum                       (XXXX XXXX 1234)
        • Passport MRZ Checksum                     • PII Redaction
        • DL Date Range Consistency
                       │                                           │
                       └─────────────────────┬─────────────────────┘
                                             ▼
                                 [ Automated Routing Engine ]
                                  PASS | FAIL | MANUAL REVIEW
                                             │
                                             ▼
                                    [ Aggregator Agent ]
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
             [ Client JSON Response ]                    [ SQLite Audit DB ]
               Structured Output + UI                     Records & Stage Latency Logs
```

---

## 📋 Supported Document Types

| Document | Primary Validations | Security Masking |
| :--- | :--- | :--- |
| **Aadhaar Card** | 12-digit format, Luhn algorithm checksum | **Mandatory 8-digit masking (`XXXX XXXX 1234`)** |
| **PAN Card** | Regex: `^[A-Z]{5}[0-9]{4}[A-Z]$`, Father's name | PII Redaction in logs |
| **Voter ID (EPIC)** | EPIC registration code, Constituency parsing | Compliant storage |
| **Driving Licence** | Validity range (`issue_date < expiry_date`), Expiry check | Vehicle class array |
| **Passport** | ICAO Doc 9303 TD3 MRZ check digits, visual cross-match | Passport number redaction |

---

## 🚦 Automated Routing Matrix

The automated routing engine evaluates validation checks, confidence thresholds, and missing fields:

| Decision | Trigger Conditions | Action |
| :--- | :--- | :--- |
| **`PASS`** | • Document recognized with confidence $\ge 0.75$<br>• All mandatory fields extracted with high confidence<br>• All checksums (Luhn, PAN, MRZ) verified<br>• Zero critical warnings | Instant approval; webhook trigger |
| **`MANUAL REVIEW`** | • Low scan clarity (`low_scan_quality_overall`)<br>• Field confidence below 65% on non-critical fields<br>• Minor date inconsistencies<br>• Unreadable address or secondary fields | Forwarded to human review queue with itemized flags |
| **`FAIL`** | • Checksum mismatch (Aadhaar Luhn failed, MRZ check digit failed)<br>• Invalid PAN structure<br>• Expired driving licence or passport<br>• Cross-field discrepancy (MRZ $\neq$ Visual passport number)<br>• Missing critical mandatory identity fields | Immediate rejection with failure reasons |

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+ or Docker
- Tesseract OCR engine (optional for local mock mode; included in Docker)
- Groq API Key ([console.groq.com](https://console.groq.com))

### 2. Local Setup
```bash
# Clone the repository
git clone https://github.com/Shriyansh212/loan_document_verification.git
cd loan_document_verification

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Add your GROQ_API_KEY in .env

# Run FastAPI server
python main.py
```

The application will be accessible at:
- **Interactive Verification Studio**: `http://localhost:8000`
- **Swagger / OpenAPI Documentation**: `http://localhost:8000/docs`
- **Health Check**: `http://localhost:8000/health`
- **Document Capabilities Showcase**: `http://localhost:8000/demo`

---

## 🐳 Docker Deployment

The included multi-stage `Dockerfile` packages Debian slim, Tesseract OCR with Hindi and English language packs, OpenCV dependencies, and SQLite:

```bash
# Build Docker image
docker build -t doc-verification-pipeline .

# Run Docker container
docker run -p 8000:8000 -e GROQ_API_KEY="your_api_key_here" doc-verification-pipeline
```

### One-Click Cloud Deployment
The repository includes a ready-to-deploy `render.yaml` blueprint:
1. Push this repository to your GitHub account (`Shriyansh212`).
2. Log into [Render.com](https://render.com) and click **New > Blueprint**.
3. Select your repository — Render automatically builds the Docker container and assigns a live HTTPS URL!

---

## 📡 REST API Reference

### 1. Verify Document
`POST /api/v1/kyc/process` (Multipart form-data)
```bash
curl -X POST "http://localhost:8000/api/v1/kyc/process" \
  -H "accept: application/json" \
  -F "file=@sample_aadhaar.png;type=image/png"
```

**Response (`HTTP 200`):**
```json
{
  "verification_id": "verif_20261119_3a91b2c4",
  "document_type": "aadhaar",
  "confidence": 0.98,
  "routing_status": "PASS",
  "routing_reasons": [
    "Document format identified and validated with high confidence",
    "All mandatory identity fields successfully extracted and verified",
    "All cryptographic/format checksums passed",
    "Mandatory 8-digit Aadhaar PII masking enforced"
  ],
  "fields": {
    "name": "Shriyansh Gupta",
    "dob": "1998-05-14",
    "gender": "M",
    "address": "42 Silicon Enclave, Indiranagar, Bengaluru, Karnataka 560038",
    "aadhaar_number": "XXXX XXXX 7192"
  },
  "masked": true,
  "field_level_scores": {
    "name": 0.96,
    "dob": 0.98,
    "gender": 0.97,
    "aadhaar_number": 0.99,
    "address": 0.89
  },
  "extraction_warnings": [],
  "risk_score": 0.05,
  "processing_time_ms": 342.5,
  "audit_trail": [
    {
      "stage_name": "Ingestion & Extraction",
      "status": "SUCCESS",
      "execution_time_ms": 42.1,
      "input_summary": "File: sample_aadhaar.png (124 KB)",
      "output_summary": "Extracted 248 chars via OCR"
    },
    {
      "stage_name": "Document Classification",
      "status": "SUCCESS",
      "execution_time_ms": 12.3,
      "input_summary": "Fuzzy keyword matching",
      "output_summary": "Classified as 'aadhaar' with 100% confidence"
    },
    {
      "stage_name": "LLM Field Extraction",
      "status": "SUCCESS",
      "execution_time_ms": 210.4,
      "input_summary": "Groq Llama 3.3 schema-guided extraction",
      "output_summary": "Extracted 5 structured fields"
    },
    {
      "stage_name": "Validation & Security Masking",
      "status": "SUCCESS",
      "execution_time_ms": 8.7,
      "input_summary": "Luhn check & PII Masker",
      "output_summary": "Masking applied: True, Warnings: 0"
    },
    {
      "stage_name": "Automated Routing Decision",
      "status": "SUCCESS",
      "execution_time_ms": 2.1,
      "input_summary": "Risk Score: 0.05",
      "output_summary": "Decision: PASS (4 policy criteria)"
    }
  ]
}
```

### 2. Instant 1-Click Sample Test
`POST /api/v1/kyc/sample/{sample_key}`
- Supported sample keys: `aadhaar_pass`, `pan_pass`, `voter_pass`, `passport_pass`, `blurry_review`, `invalid_fail`

### 3. List SQL Verification Records
`GET /api/v1/kyc/records?status=PASS&limit=20`

### 4. Fetch Pipeline Analytics
`GET /api/v1/kyc/stats`

---

## 🧪 Testing

Run the test suite:
```bash
python tests/run_tests.py
```

---

## 🛡️ Security & Compliance

- **Zero-Unmasked Aadhaar Storage**: The masking agent replaces the first 8 digits with `XXXX XXXX` before saving to SQLite or serializing into JSON.
- **PII Logging Filter**: `PIIRedactionFilter` intercepts Python `logging` streams and sanitizes Aadhaar numbers, PAN codes, and passport identifiers.
- **Fail-Safe Processing**: Memory buffers are cleaned and temporary uploaded files are unlinked immediately after processing.

---

## 👤 Author

**Shriyansh Gupta**
- GitHub: [@Shriyansh212](https://github.com/Shriyansh212)
- Email: shriyanshg54@gmail.com
