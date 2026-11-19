"""
Extractor Agent - LLM-based field extraction using schema-guided prompts.
Powered by Groq Llama with intelligent heuristic fallback for offline/demo operation.
"""

import json
import os
import re
from typing import Any, Dict, Optional
from models.schemas import AgentResponse, ExtractorResult, SUPPORTED_DOCUMENT_TYPES
from utils.logger import get_logger

logger = get_logger(__name__)


class ExtractorAgent:
    """
    Extractor Agent - Extracts structured fields using LLM with schema-guided prompts.
    
    Uses Groq Llama (llama-3.3-70b-versatile) with strict JSON output schemas.
    Includes heuristic fallback extraction for local test suites and offline demos.
    """

    def __init__(self):
        self.name = "Extractor Agent"
        self.groq_client = None

        api_key = os.getenv("GROQ_API_KEY")
        if api_key and api_key.strip() and not api_key.startswith("gsk_placeholder"):
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=api_key)
                logger.info("Groq client initialized with Llama-3.3-70B model")
            except Exception as e:
                logger.warning(f"Could not initialize Groq client: {e}")
        else:
            logger.info("GROQ_API_KEY not provided. Fallback heuristic extraction engine enabled.")

        self.extraction_prompts = {
            "aadhaar": self._create_aadhaar_prompt(),
            "pan": self._create_pan_prompt(),
            "voter_id": self._create_voter_id_prompt(),
            "driving_licence": self._create_driving_licence_prompt(),
            "passport": self._create_passport_prompt(),
        }

    async def extract_fields(self, raw_text: str, document_type: str) -> AgentResponse:
        """
        Extract structured fields from raw text using Groq Llama with heuristic fallback.
        """
        try:
            logger.info(f"Starting field extraction for document type: {document_type}")

            if document_type not in SUPPORTED_DOCUMENT_TYPES:
                return AgentResponse(
                    success=False,
                    error=f"Unsupported document type: {document_type}",
                )

            if not raw_text or not raw_text.strip():
                return AgentResponse(
                    success=False,
                    error="No text provided for extraction",
                )

            # Strategy A: Use Groq Llama if API key is active
            if self.groq_client:
                try:
                    logger.info("Calling Groq Llama-3.3-70B for field extraction...")
                    system_prompt = self.extraction_prompts[document_type]
                    user_prompt = f"Extract fields from this {document_type} document:\n\n{raw_text}"

                    response = self.groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=1000,
                        temperature=0.1,
                    )

                    response_text = response.choices[0].message.content.strip()
                    extracted_data = self._parse_extraction_response(response_text)

                    if extracted_data:
                        fields = {k: v for k, v in extracted_data.items() if k != "field_confidence"}
                        field_confidence = extracted_data.get("field_confidence", {})
                        validated_fields = self._validate_extracted_fields(fields, document_type)

                        return AgentResponse(
                            success=True,
                            data=ExtractorResult(
                                fields=validated_fields,
                                field_confidence=field_confidence,
                            ),
                        )
                except Exception as e:
                    logger.warning(f"Groq API call failed ({e}). Falling back to heuristic extraction.")

            # Strategy B: Heuristic fallback extraction
            logger.info("Using intelligent regex/pattern fallback extractor...")
            fields, field_confidence = self._heuristic_extract(raw_text, document_type)
            validated_fields = self._validate_extracted_fields(fields, document_type)

            return AgentResponse(
                success=True,
                data=ExtractorResult(
                    fields=validated_fields,
                    field_confidence=field_confidence,
                ),
            )

        except Exception as e:
            logger.error(f"Error in field extraction: {e}")
            return AgentResponse(
                success=False,
                error=f"Field extraction failed: {str(e)}",
            )

    def _parse_extraction_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from LLM output, extracting from markdown code blocks if needed."""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Search for ```json ... ``` code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Search for bare {...}
        brace_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _validate_extracted_fields(self, fields: Dict[str, Any], document_type: str) -> Dict[str, Any]:
        """Validate fields against schema and strip nulls."""
        schema_class = SUPPORTED_DOCUMENT_TYPES.get(document_type)
        if not schema_class:
            return fields

        try:
            validated = schema_class(**fields)
            return {k: v for k, v in validated.model_dump().items() if v is not None}
        except Exception as e:
            logger.warning(f"Field validation warning: {e}")
            return {k: v for k, v in fields.items() if v is not None}

    def _heuristic_extract(self, text: str, doc_type: str) -> tuple[Dict[str, Any], Dict[str, float]]:
        """
        Fast, backtracking-safe heuristic extraction for offline demo / fallback testing.
        """
        fields: Dict[str, Any] = {}
        conf: Dict[str, float] = {}

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Date of Birth pattern
        for line in lines:
            if any(k in line.lower() for k in ["dob", "birth", "जन्म", "date of birth"]):
                d_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", line)
                if d_match:
                    raw_d = d_match.group(1).replace("/", "-")
                    pts = raw_d.split("-")
                    if len(pts[0]) == 4:
                        fields["dob"] = f"{pts[0]}-{pts[1]}-{pts[2]}"
                    else:
                        fields["dob"] = f"{pts[2]}-{pts[1]}-{pts[0]}"
                    conf["dob"] = 0.95
                    break

        if "dob" not in fields:
            d_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
            if d_match:
                fields["dob"] = d_match.group(1)
                conf["dob"] = 0.90

        # 2. Document specific fields
        if doc_type == "aadhaar":
            # 12 digits
            uid_match = re.search(r"\b(\d{4}\s\d{4}\s\d{4}|\d{12})\b", text)
            if uid_match:
                fields["aadhaar_number"] = uid_match.group(1).replace(" ", "")
                conf["aadhaar_number"] = 0.98

            # Gender
            text_lower = text.lower()
            if "female" in text_lower or "महिला" in text_lower:
                fields["gender"] = "F"
                conf["gender"] = 0.97
            elif "male" in text_lower or "पुरुष" in text_lower:
                fields["gender"] = "M"
                conf["gender"] = 0.97

            # Name: check lines after 'To,' or containing 'Name:'
            for i, line in enumerate(lines):
                if line.startswith("To,") and i + 1 < len(lines):
                    fields["name"] = lines[i + 1]
                    conf["name"] = 0.94
                    break
                elif "name:" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) > 1 and len(parts[1].strip()) >= 2:
                        fields["name"] = parts[1].strip()
                        conf["name"] = 0.92
                        break

            if "name" not in fields:
                for line in lines:
                    if len(line.split()) in [2, 3] and not re.search(r"[\d@#$%/\\|]", line):
                        if not any(k in line.lower() for k in ["government", "india", "aadhaar", "authority", "unique"]):
                            fields["name"] = line
                            conf["name"] = 0.85
                            break

            # Address
            for line in lines:
                if line.lower().startswith("address:") or "पता:" in line:
                    parts = re.split(r"[:：]", line, 1)
                    if len(parts) > 1:
                        fields["address"] = parts[1].strip()
                        conf["address"] = 0.88
                        break

        elif doc_type == "pan":
            pan_match = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", text)
            if pan_match:
                fields["pan_number"] = pan_match.group(1)
                conf["pan_number"] = 0.99

            for line in lines:
                l_lower = line.lower()
                if "father" in l_lower and ":" in line:
                    fields["fathers_name"] = line.split(":", 1)[1].strip()
                    conf["fathers_name"] = 0.90
                elif "name:" in l_lower and "father" not in l_lower:
                    fields["name"] = line.split(":", 1)[1].strip()
                    conf["name"] = 0.94

            if "name" not in fields:
                for line in lines:
                    if line.isupper() and len(line.split()) in [2, 3]:
                        if not any(k in line for k in ["INCOME", "TAX", "PERMANENT", "ACCOUNT", "GOVT", "DEPARTMENT"]):
                            fields["name"] = line
                            conf["name"] = 0.88
                            break

        elif doc_type == "voter_id":
            epic_match = re.search(r"\b([A-Z]{3}\d{7})\b", text)
            if epic_match:
                fields["voter_id_number"] = epic_match.group(1)
                conf["voter_id_number"] = 0.98

            for line in lines:
                l_lower = line.lower()
                if "name:" in l_lower and "father" not in l_lower:
                    fields["name"] = line.split(":", 1)[1].strip()
                    conf["name"] = 0.93
                elif "father" in l_lower and ":" in line:
                    fields["relative_name"] = line.split(":", 1)[1].strip()
                    conf["relative_name"] = 0.90
                elif "constituency:" in l_lower:
                    fields["constituency"] = line.split(":", 1)[1].strip()
                    conf["constituency"] = 0.91

        elif doc_type == "driving_licence":
            dl_match = re.search(r"\b([A-Z]{2}\d{13,15}|[A-Z]{2}-\d{13,15})\b", text)
            if dl_match:
                fields["dl_number"] = dl_match.group(1).replace("-", "")
                conf["dl_number"] = 0.98

            for line in lines:
                if "name:" in line.lower():
                    fields["name"] = line.split(":", 1)[1].strip()
                    conf["name"] = 0.92

            dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
            if len(dates) >= 2:
                fields["valid_from"] = dates[0]
                fields["valid_until"] = dates[1]
                conf["valid_from"] = 0.91
                conf["valid_until"] = 0.91
            elif len(dates) == 1:
                fields["valid_until"] = dates[0]
                conf["valid_until"] = 0.90

            classes = re.findall(r"\b(LMV|MCWG|MCWOG|TRANS|HGMV)\b", text)
            if classes:
                fields["vehicle_classes"] = list(set(classes))
                conf["vehicle_classes"] = 0.95

        elif doc_type == "passport":
            p_match = re.search(r"\b([A-Z]\d{7})\b", text)
            if p_match:
                fields["passport_number"] = p_match.group(1)
                conf["passport_number"] = 0.99

            for line in lines:
                if "name:" in line.lower():
                    fields["name"] = line.split(":", 1)[1].strip()
                    conf["name"] = 0.95

            fields["nationality"] = "IND"
            conf["nationality"] = 0.99

            exp_match = re.search(r"(?:Expiry Date|Expiry)[:\s]*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
            if exp_match:
                fields["expiry_date"] = exp_match.group(1)
                conf["expiry_date"] = 0.93

            mrz_match = re.search(r"(P<IND[A-Z<]+)", text)
            if mrz_match:
                fields["mrz_line"] = mrz_match.group(1)
                conf["mrz_line"] = 0.96

        return fields, conf

    def _create_aadhaar_prompt(self) -> str:
        return """You are an OCR post-processor that extracts structured data from Aadhaar cards.
Extract the following fields from the raw text:
- name: Full name as printed on card (string)
- dob: Date of birth in YYYY-MM-DD format (string)
- gender: Gender as M, F, or O (string)
- address: Full address as printed (string)
- aadhaar_number: 12-digit Aadhaar number with no spaces (string)
- field_confidence: Confidence score 0.0-1.0 for each field (object)

Return ONLY valid JSON with these exact keys. If a field is unreadable, emit null."""

    def _create_pan_prompt(self) -> str:
        return """You are an OCR post-processor that extracts structured data from PAN cards.
Extract the following fields from the raw text:
- name: Full name as printed on card (string)
- fathers_name: Father's name as printed (string)
- dob: Date of birth in YYYY-MM-DD format (string)
- pan_number: 10-character PAN number in format ABCDE1234F (string)
- field_confidence: Confidence score 0.0-1.0 for each field (object)

Return ONLY valid JSON with these exact keys. If a field is unreadable, emit null."""

    def _create_voter_id_prompt(self) -> str:
        return """You are an OCR post-processor that extracts structured data from Voter ID cards.
Extract the following fields from the raw text:
- name: Full name as printed on card (string)
- relative_name: Father's or husband's name (string)
- dob: Date of birth in YYYY-MM-DD format (string)
- voter_id_number: Voter ID number (string)
- address: Full address as printed (string)
- constituency: Electoral constituency name (string)
- field_confidence: Confidence score 0.0-1.0 for each field (object)

Return ONLY valid JSON with these exact keys. If a field is unreadable, emit null."""

    def _create_driving_licence_prompt(self) -> str:
        return """You are an OCR post-processor that extracts structured data from Driving Licence cards.
Extract the following fields from the raw text:
- name: Full name as printed on licence (string)
- dob: Date of birth in YYYY-MM-DD format (string)
- dl_number: Driving licence number (string)
- valid_from: Issue date in YYYY-MM-DD format (string)
- valid_until: Expiry date in YYYY-MM-DD format (string)
- vehicle_classes: Array of vehicle class codes (array)
- address: Full address as printed (string)
- field_confidence: Confidence score 0.0-1.0 for each field (object)

Return ONLY valid JSON with these exact keys. If a field is unreadable, emit null."""

    def _create_passport_prompt(self) -> str:
        return """You are an OCR post-processor that extracts structured data from Indian passports.
Extract the following fields from the raw text:
- name: Full name as printed in passport (string)
- dob: Date of birth in YYYY-MM-DD format (string)
- passport_number: Passport number (string)
- nationality: 3-letter country code like IND (string)
- expiry_date: Passport expiry date in YYYY-MM-DD format (string)
- mrz_line: Full MRZ line string (string)
- field_confidence: Confidence score 0.0-1.0 for each field (object)

Return ONLY valid JSON with these exact keys. If a field is unreadable, emit null."""
