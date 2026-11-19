"""
Classifier Agent - Document type identification
Strategy: fuzzy keyword pre-filter → LLM classification (primary) → reject if < 0.3
"""

import json
import os
from typing import Dict, List, Optional
from models.schemas import ClassifierResult, AgentResponse
from utils.logger import get_logger

logger = get_logger(__name__)

def calculate_similarity(sub: str, full: str) -> float:
    """Fast, zero-backtracking substring and keyword similarity check."""
    if sub in full:
        return 1.0
    sub_words = sub.split()
    if len(sub_words) > 1 and all(w in full for w in sub_words):
        return 0.95
    for line in full.splitlines():
        l_strip = line.strip()
        if sub in l_strip:
            return 1.0
    return 0.0

# Fuzzy keyword sets per document type
KEYWORD_MAP = {
    "aadhaar": ["UNIQUE IDENTIFICATION", "AADHAAR", "आधार", "UIDAI", "GOVERNMENT OF INDIA", "MERA AADHAAR"],
    "pan": ["INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER", "INCOME TAX", "GOVT. OF INDIA"],
    "voter_id": ["ELECTION COMMISSION", "ELECTORS PHOTO", "ELECTORAL", "BHARAT NIRVACHAN AAYOG", "IDENTITY CARD"],
    "driving_licence": ["DRIVING LICENCE", "DRIVING LICENSE", "MOTOR VEHICLES", "TRANSPORT DEPARTMENT", "UNION OF INDIA"],
    "passport": ["REPUBLIC OF INDIA", "PASSPORT", "MINISTRY OF EXTERNAL AFFAIRS", "PASSPORT NO"],
}

LLM_PROMPT = """Look at this OCR text from an Indian identity document.
Identify the document type. Return ONLY a JSON object, nothing else:
{{"document_type": "<aadhaar|pan|voter_id|driving_licence|passport|unknown>", "confidence": <0.0-1.0>}}

OCR text:
{raw_text}"""


class ClassifierAgent:
    def __init__(self):
        self.name = "Classifier Agent"
        self.min_confidence = 0.3
        self.groq_client = None

        api_key = os.getenv("GROQ_API_KEY")
        if api_key and api_key.strip() and not api_key.startswith("gsk_placeholder"):
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=api_key)
            except Exception as e:
                logger.warning(f"Could not load Groq client for classifier: {e}")

    async def classify_document(self, raw_text: str) -> AgentResponse:
        try:
            if not raw_text or not raw_text.strip():
                return AgentResponse(success=False, error="No text provided for classification")

            logger.info(f"Classifying raw text (length: {len(raw_text)} chars)...")

            # Step 1: Fuzzy keyword pre-filter (fast, zero API cost)
            fuzzy_result = self._fuzzy_keyword_classify(raw_text)
            if fuzzy_result and fuzzy_result["confidence"] >= 0.85:
                logger.info(f"Fuzzy keyword match: {fuzzy_result['document_type']} ({fuzzy_result['confidence']:.2f})")
                return AgentResponse(
                    success=True,
                    data=ClassifierResult(
                        document_type=fuzzy_result["document_type"],
                        confidence=fuzzy_result["confidence"],
                    ),
                )

            # Step 2: LLM classification if available
            llm_result = await self._classify_by_llm(raw_text)
            if llm_result and llm_result["document_type"] and llm_result["confidence"] >= self.min_confidence:
                logger.info(f"LLM classification: {llm_result['document_type']} ({llm_result['confidence']:.2f})")
                return AgentResponse(
                    success=True,
                    data=ClassifierResult(
                        document_type=llm_result["document_type"],
                        confidence=llm_result["confidence"],
                    ),
                )

            # Step 3: Fall back to fuzzy result if LLM failed or wasn't configured
            if fuzzy_result and fuzzy_result["confidence"] >= self.min_confidence:
                logger.info(f"Falling back to fuzzy: {fuzzy_result['document_type']} ({fuzzy_result['confidence']:.2f})")
                return AgentResponse(
                    success=True,
                    data=ClassifierResult(
                        document_type=fuzzy_result["document_type"],
                        confidence=fuzzy_result["confidence"],
                    ),
                )

            logger.info("Classification failed — no match above threshold")
            return AgentResponse(success=False, error="unsupported_document_type")

        except Exception as e:
            logger.error(f"Classification error: {e}")
            return AgentResponse(success=False, error=f"Classification failed: {e}")

    def _fuzzy_keyword_classify(self, text: str) -> Optional[Dict]:
        text_upper = text.upper()
        best_type, best_score = None, 0.0

        for doc_type, keywords in KEYWORD_MAP.items():
            for kw in keywords:
                score = calculate_similarity(kw, text_upper)
                if score > best_score:
                    best_score = score
                    best_type = doc_type

        if best_type and best_score >= 0.65:
            return {"document_type": best_type, "confidence": min(1.0, best_score)}
        return None

    async def _classify_by_llm(self, text: str) -> Optional[Dict]:
        if not self.groq_client:
            return None
        try:
            truncated = text[:2000]
            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": LLM_PROMPT.format(raw_text=truncated)}],
                max_tokens=100,
                temperature=0.1,
            )
            resp_text = response.choices[0].message.content.strip()
            start = resp_text.find("{")
            end = resp_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(resp_text[start:end])
                doc_type = data.get("document_type", "unknown")
                conf = float(data.get("confidence", 0.0))
                valid_types = {"aadhaar", "pan", "voter_id", "driving_licence", "passport"}
                if doc_type in valid_types:
                    return {"document_type": doc_type, "confidence": max(0.0, min(1.0, conf))}
            return None
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return None

    def get_supported_types(self) -> List[str]:
        return list(KEYWORD_MAP.keys())
