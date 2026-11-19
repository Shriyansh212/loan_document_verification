"""
Zero-dependency test runner using Python's built-in unittest module.
"""

import os
import sys
import unittest

# Add workspace to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.classifier import ClassifierAgent
from agents.router import RoutingAgent
from agents.validator import ValidatorAgent
from agents.masker import MaskerAgent
from database.connection import init_db
from database.crud import (
    save_verification_record,
    get_verification_record,
    list_verification_records,
    get_verification_stats,
)


class TestDocumentVerificationPipeline(unittest.TestCase):
    def setUp(self):
        init_db()
        self.classifier = ClassifierAgent()
        self.router = RoutingAgent()
        self.validator = ValidatorAgent()
        self.masker = MaskerAgent()

    def test_classifier_fuzzy_matching(self):
        aadhaar_text = "GOVERNMENT OF INDIA UNIQUE IDENTIFICATION AUTHORITY OF INDIA आधार 984123567192"
        res = self.classifier._fuzzy_keyword_classify(aadhaar_text)
        self.assertIsNotNone(res)
        self.assertEqual(res["document_type"], "aadhaar")

        pan_text = "INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER ABCDE1234F"
        res_pan = self.classifier._fuzzy_keyword_classify(pan_text)
        self.assertIsNotNone(res_pan)
        self.assertEqual(res_pan["document_type"], "pan")

    def test_aadhaar_masking(self):
        fields = {"name": "Shriyansh Gupta", "aadhaar_number": "984123567192"}
        masked, applied = self.masker._mask_aadhaar_fields(fields)
        self.assertTrue(applied)
        self.assertTrue(masked["aadhaar_number"].startswith("XXXX XXXX"))
        self.assertTrue(masked["aadhaar_number"].endswith("7192"))

    def test_validator_pan_regex(self):
        valid_pan = {"pan_number": "ABCDE1234F"}
        warnings = self.validator._validate_pan(valid_pan)
        self.assertEqual(len(warnings), 0)

        invalid_pan = {"pan_number": "INVALID123"}
        warnings_invalid = self.validator._validate_pan(invalid_pan)
        self.assertIn("pan_format_invalid", warnings_invalid)

    def test_routing_pass(self):
        fields = {"name": "Shriyansh Gupta", "aadhaar_number": "XXXX XXXX 7192"}
        conf = {"name": 0.95, "aadhaar_number": 0.98}
        res = self.router.evaluate_routing(
            document_type="aadhaar",
            confidence=0.95,
            fields=fields,
            field_confidence=conf,
            warnings=[],
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "PASS")
        self.assertLess(res.data.risk_score, 0.2)

    def test_routing_fail(self):
        fields = {"name": "Unknown", "pan_number": "INVALID"}
        res = self.router.evaluate_routing(
            document_type="pan",
            confidence=0.90,
            fields=fields,
            field_confidence={"name": 0.9},
            warnings=["pan_format_invalid"],
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "FAIL")

    def test_routing_manual_review(self):
        fields = {"name": "Priya Sharma", "aadhaar_number": "XXXX XXXX 1234"}
        res = self.router.evaluate_routing(
            document_type="aadhaar",
            confidence=0.65,
            fields=fields,
            field_confidence={"name": 0.55},
            warnings=["low_scan_quality_overall"],
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "MANUAL_REVIEW")

    def test_database_crud_and_audit(self):
        v_id = f"test_{os.urandom(4).hex()}"
        rec = {
            "verification_id": v_id,
            "document_type": "aadhaar",
            "filename": "sample.png",
            "confidence": 0.98,
            "routing_status": "PASS",
            "routing_reasons": ["Luhn check passed"],
            "extracted_fields": {"name": "Shriyansh"},
            "masked_fields": {"name": "Shriyansh"},
            "field_level_scores": {"name": 0.98},
            "warnings": [],
            "masked": True,
            "processing_time_ms": 115.0,
        }
        audit = [
            {
                "stage_name": "Ingestion",
                "status": "SUCCESS",
                "execution_time_ms": 12.0,
                "input_summary": "file.png",
                "output_summary": "raw text",
                "details": {},
            }
        ]
        saved_id = save_verification_record(rec, audit)
        self.assertEqual(saved_id, v_id)

        fetched = get_verification_record(v_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["routing_status"], "PASS")
        self.assertEqual(len(fetched["audit_logs"]), 1)

        stats = get_verification_stats()
        self.assertGreaterEqual(stats["total_processed"], 1)


if __name__ == "__main__":
    unittest.main()
