"""
Test suite for KYC Document Processing Pipeline agents
"""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from agents.classifier import ClassifierAgent
from agents.extractor import ExtractorAgent
from agents.validator import ValidatorAgent
from agents.masker import MaskerAgent
from agents.aggregator import AggregatorAgent
from models.schemas import ValidatorResult, MaskerResult, ClassifierResult, ExtractorResult


class TestClassifierAgent:
    """Test cases for ClassifierAgent"""
    
    @pytest.fixture
    def classifier_agent(self):
        return ClassifierAgent()
    
    def test_classify_aadhaar_by_keywords(self, classifier_agent):
        """Test Aadhaar classification using keywords"""
        aadhaar_text = """
        GOVERNMENT OF INDIA
        UNIQUE IDENTIFICATION AUTHORITY OF INDIA
        आधार
        Name: PRIYA SHARMA
        DOB: 12/04/1990
        1234 5678 9012
        """
        
        result = classifier_agent._fuzzy_keyword_classify(aadhaar_text)
        assert result["document_type"] == "aadhaar"
        assert result["confidence"] > 0.5
    
    def test_classify_pan_by_keywords(self, classifier_agent):
        """Test PAN classification using keywords"""
        pan_text = """
        INCOME TAX DEPARTMENT
        GOVT. OF INDIA
        PERMANENT ACCOUNT NUMBER
        Name: RAJESH KUMAR
        Father's Name: SURESH KUMAR
        ABCDE1234F
        """
        
        result = classifier_agent._fuzzy_keyword_classify(pan_text)
        assert result["document_type"] == "pan"
        assert result["confidence"] > 0.7
    
    def test_classify_voter_id_by_keywords(self, classifier_agent):
        """Test Voter ID classification using keywords"""
        voter_text = """
        ELECTION COMMISSION OF INDIA
        ELECTORAL PHOTO IDENTITY CARD
        Name: ANITA SINGH
        Father's Name: RAM SINGH
        Constituency: NOIDA
        """
        
        result = classifier_agent._fuzzy_keyword_classify(voter_text)
        assert result["document_type"] == "voter_id"
        assert result["confidence"] > 0.3
    
    def test_classify_driving_licence_by_keywords(self, classifier_agent):
        """Test Driving Licence classification using keywords"""
        dl_text = """
        TRANSPORT DEPARTMENT
        DRIVING LICENCE
        Name: VIKRAM SINGH  
        DL NO: DL1420110012345
        CLASS OF VEHICLE: LMV/MCWG
        """
        
        result = classifier_agent._fuzzy_keyword_classify(dl_text)
        assert result["document_type"] == "driving_licence"
        assert result["confidence"] > 0.5
    
    def test_classify_passport_by_keywords(self, classifier_agent):
        """Test Passport classification using keywords"""
        passport_text = """
        REPUBLIC OF INDIA
        PASSPORT
        MINISTRY OF EXTERNAL AFFAIRS
        Name: MEERA PATEL
        Place of Birth: MUMBAI
        P<INDPATEL<<MEERA<<<
        """
        
        result = classifier_agent._fuzzy_keyword_classify(passport_text)
        assert result["document_type"] == "passport"
        assert result["confidence"] > 0.5
    
    def test_classify_unknown_document(self, classifier_agent):
        """Test classification of unknown document type"""
        unknown_text = """
        UTILITY BILL
        ELECTRICITY DEPARTMENT
        Customer Name: JOHN DOE
        Bill Amount: Rs. 1500
        """
        
        result = classifier_agent._fuzzy_keyword_classify(unknown_text)
        assert result is None or result["confidence"] < 0.5


class TestValidatorAgent:
    """Test cases for ValidatorAgent"""
    
    @pytest.fixture
    def validator_agent(self):
        return ValidatorAgent()
    
    @pytest.mark.asyncio
    async def test_validate_aadhaar_fields(self, validator_agent):
        """Test Aadhaar field validation"""
        # Valid Aadhaar fields
        valid_fields = {
            "name": "PRIYA SHARMA",
            "dob": "1990-04-12",
            "gender": "F",
            "address": "12 MG Road, Bengaluru",
            "aadhaar_number": "234567890129"  # Valid Luhn checksum
        }
        
        result = await validator_agent.validate_fields(valid_fields, "aadhaar")
        assert result.success
        assert result.data.is_valid
        
        # Invalid Aadhaar number
        invalid_fields = {
            "aadhaar_number": "123456789012",  # Invalid Luhn
            "gender": "X"  # Invalid gender
        }
        
        result = await validator_agent.validate_fields(invalid_fields, "aadhaar")
        assert result.success
        assert "aadhaar_luhn_failed" in result.data.warnings
        assert "aadhaar_invalid_gender" in result.data.warnings
    
    @pytest.mark.asyncio
    async def test_validate_pan_fields(self, validator_agent):
        """Test PAN field validation"""
        # Valid PAN
        valid_fields = {
            "name": "RAJESH KUMAR",
            "pan_number": "ABCDE1234F",
            "dob": "1985-07-20"
        }
        
        result = await validator_agent.validate_fields(valid_fields, "pan")
        assert result.success
        assert len(result.data.warnings) == 0
        
        # Invalid PAN format
        invalid_fields = {
            "pan_number": "INVALID123"
        }
        
        result = await validator_agent.validate_fields(invalid_fields, "pan")
        assert result.success
        assert "pan_format_invalid" in result.data.warnings
    
    @pytest.mark.asyncio
    async def test_validate_driving_licence_expiry(self, validator_agent):
        """Test Driving Licence expiry validation"""
        from datetime import date, timedelta
        
        # Expired licence
        expired_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        expired_fields = {
            "name": "VIKRAM SINGH",
            "valid_until": expired_date
        }
        
        result = await validator_agent.validate_fields(expired_fields, "driving_licence")
        assert result.success
        assert "dl_expired" in result.data.warnings
        
        # Valid licence
        future_date = (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
        valid_fields = {
            "name": "VIKRAM SINGH",
            "valid_until": future_date
        }
        
        result = await validator_agent.validate_fields(valid_fields, "driving_licence")
        assert result.success
        assert "dl_expired" not in result.data.warnings
    
    def test_luhn_validation(self, validator_agent):
        """Test Luhn algorithm validation"""
        # Valid Luhn numbers
        assert validator_agent._validate_luhn("4532015112830366")
        assert validator_agent._validate_luhn("234567890129")
        
        # Invalid Luhn numbers
        assert not validator_agent._validate_luhn("123456789012")
        assert not validator_agent._validate_luhn("1111111111111")


class TestMaskerAgent:
    """Test cases for MaskerAgent"""
    
    @pytest.fixture
    def masker_agent(self):
        return MaskerAgent()
    
    @pytest.mark.asyncio
    async def test_mask_aadhaar_number(self, masker_agent):
        """Test Aadhaar number masking"""
        fields = {
            "name": "PRIYA SHARMA",
            "aadhaar_number": "123456789012"
        }
        
        result = await masker_agent.mask_fields(fields, "aadhaar")
        assert result.success
        assert result.data.masking_applied
        assert result.data.masked_fields["aadhaar_number"] == "XXXX XXXX 9012"
        assert result.data.masked_fields["name"] == "PRIYA SHARMA"  # Unchanged
    
    @pytest.mark.asyncio
    async def test_mask_aadhaar_with_spaces(self, masker_agent):
        """Test Aadhaar masking with spaces in input"""
        fields = {
            "aadhaar_number": "1234 5678 9012"
        }
        
        result = await masker_agent.mask_fields(fields, "aadhaar")
        assert result.success
        assert result.data.masked_fields["aadhaar_number"] == "XXXX XXXX 9012"
    
    @pytest.mark.asyncio 
    async def test_no_masking_for_non_aadhaar(self, masker_agent):
        """Test that non-Aadhaar documents don't get masked"""
        fields = {
            "pan_number": "ABCDE1234F",
            "name": "RAJESH KUMAR"
        }
        
        result = await masker_agent.mask_fields(fields, "pan")
        assert result.success
        assert not result.data.masking_applied
        assert result.data.masked_fields == fields  # Unchanged
    
    def test_mask_aadhaar_number_direct(self, masker_agent):
        """Test direct Aadhaar number masking function"""
        # Test various formats
        assert masker_agent._mask_aadhaar_number("123456789012") == "XXXX XXXX 9012"
        assert masker_agent._mask_aadhaar_number("1234 5678 9012") == "XXXX XXXX 9012"
        assert masker_agent._mask_aadhaar_number("1234-5678-9012") == "XXXX XXXX 9012"
        
        # Test invalid formats
        with pytest.raises(ValueError):
            masker_agent._mask_aadhaar_number("12345")  # Too short
        
        with pytest.raises(ValueError):
            masker_agent._mask_aadhaar_number("12345678901234")  # Too long
        
        with pytest.raises(ValueError):
            masker_agent._mask_aadhaar_number("")  # Empty


class TestAggregatorAgent:
    """Test cases for AggregatorAgent"""
    
    @pytest.fixture
    def aggregator_agent(self):
        return AggregatorAgent()
    
    @pytest.mark.asyncio
    async def test_aggregate_aadhaar_results(self, aggregator_agent):
        """Test aggregation of Aadhaar processing results"""
        validator_result = ValidatorResult(
            warnings=["low_scan_quality_on_address"],
            is_valid=True
        )
        
        masker_result = MaskerResult(
            masked_fields={
                "name": "PRIYA SHARMA",
                "aadhaar_number": "XXXX XXXX 9012",
                "dob": "1990-04-12"
            },
            masking_applied=True
        )
        
        field_confidence = {
            "name": 0.99,
            "aadhaar_number": 0.95,
            "dob": 0.98
        }
        
        result = await aggregator_agent.aggregate_results(
            doc_type="aadhaar",
            confidence=0.97,
            field_confidence=field_confidence,
            validator_result=validator_result,
            masker_result=masker_result
        )
        
        assert result.success
        assert result.data.document_type == "aadhaar"
        assert result.data.confidence == 0.97
        assert result.data.masked
        assert result.data.fields["aadhaar_number"] == "XXXX XXXX 9012"
        assert result.data.extraction_warnings == ["low_scan_quality_on_address"]
    
    def test_properly_masked_aadhaar_validation(self, aggregator_agent):
        """Test validation of properly masked Aadhaar numbers"""
        assert aggregator_agent._is_properly_masked_aadhaar("XXXX XXXX 1234")
        assert not aggregator_agent._is_properly_masked_aadhaar("123456789012")
        assert not aggregator_agent._is_properly_masked_aadhaar("XXXX XXXX 12345")  # Too many digits
        assert not aggregator_agent._is_properly_masked_aadhaar("XXX XXXX 1234")   # Wrong format
    
    def test_create_error_response(self, aggregator_agent):
        """Test error response creation"""
        error_response = aggregator_agent.create_error_response(
            "unsupported_document_type",
            "Document could not be classified"
        )
        
        assert error_response.document_type is None
        assert error_response.confidence == 0.0
        assert error_response.fields == {}
        assert not error_response.masked
        assert error_response.error == "unsupported_document_type"


class TestIntegrationScenarios:
    """Integration test scenarios covering the 5 required test cases"""
    
    @pytest.mark.asyncio
    async def test_scenario_1_aadhaar_clean_scan(self):
        """Test case 1: Aadhaar clean scan - verify masking applied, all fields extracted"""
        # This would typically use a real image file in practice
        mock_aadhaar_text = """
        GOVERNMENT OF INDIA
        UNIQUE IDENTIFICATION AUTHORITY OF INDIA
        आधार
        Name: PRIYA SHARMA
        DOB: 12/04/1990
        Female
        Address: 12 MG Road, Bengaluru, Karnataka 560001
        1234 5678 9012
        """
        
        # Test classification
        classifier = ClassifierAgent()
        classification = classifier._fuzzy_keyword_classify(mock_aadhaar_text)
        assert classification["document_type"] == "aadhaar"
        assert classification["confidence"] > 0.5
        
        # Test masking
        masker = MaskerAgent()
        fields = {"aadhaar_number": "123456789012", "name": "PRIYA SHARMA"}
        mask_result = await masker.mask_fields(fields, "aadhaar")
        assert mask_result.success
        assert mask_result.data.masking_applied
        assert "XXXX XXXX" in mask_result.data.masked_fields["aadhaar_number"]
    
    @pytest.mark.asyncio
    async def test_scenario_2_pan_clean_scan(self):
        """Test case 2: PAN clean scan - verify format validation passes"""
        pan_fields = {
            "name": "RAJESH KUMAR",
            "fathers_name": "SURESH KUMAR",
            "pan_number": "ABCDE1234F",
            "dob": "1985-07-20"
        }
        
        validator = ValidatorAgent()
        result = await validator.validate_fields(pan_fields, "pan")
        assert result.success
        assert "pan_format_invalid" not in result.data.warnings
    
    @pytest.mark.asyncio
    async def test_scenario_3_degraded_scan_warnings(self):
        """Test case 3: Degraded scan - verify warnings emitted"""
        # Simulate low confidence scenario
        validator = ValidatorAgent()
        
        # Test with invalid date format (simulates OCR errors)
        degraded_fields = {
            "name": "UNCLEAR NAME",
            "dob": "1990/04/32",  # Invalid date
            "pan_number": "ABCDE123"  # Invalid format
        }
        
        result = await validator.validate_fields(degraded_fields, "pan")
        assert result.success
        assert len(result.data.warnings) > 0
        assert "pan_format_invalid" in result.data.warnings
    
    @pytest.mark.asyncio
    async def test_scenario_4_unsupported_document(self):
        """Test case 4: Unsupported document - verify graceful rejection"""
        utility_bill_text = """
        ELECTRICITY BOARD
        UTILITY BILL
        Customer: JOHN DOE
        Amount: Rs. 1500
        Due Date: 2024-01-31
        """
        
        classifier = ClassifierAgent()
        result = classifier._fuzzy_keyword_classify(utility_bill_text)
        assert result is None or result["confidence"] < 0.5
    
    @pytest.mark.asyncio
    async def test_scenario_5_expired_driving_licence(self):
        """Test case 5: Expired DL - verify warning emitted"""
        from datetime import date, timedelta
        
        expired_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        dl_fields = {
            "name": "VIKRAM SINGH",
            "dl_number": "DL1420110012345",
            "valid_until": expired_date
        }
        
        validator = ValidatorAgent()
        result = await validator.validate_fields(dl_fields, "driving_licence")
        assert result.success
        assert "dl_expired" in result.data.warnings


if __name__ == "__main__":
    pytest.main([__file__])


from agents.router import RoutingAgent
from database.crud import (
    save_verification_record,
    get_verification_record,
    list_verification_records,
    get_verification_stats,
)
from database.connection import init_db


class TestRoutingAndDatabase:
    """Test cases for Automated Routing Engine and SQLite Audit Storage"""

    def setup_method(self):
        init_db()
        self.router = RoutingAgent()

    def test_routing_pass_decision(self):
        """Test clean document routes to PASS"""
        fields = {
            "name": "Shriyansh Gupta",
            "aadhaar_number": "XXXX XXXX 7192",
            "dob": "1998-05-14",
            "gender": "M",
        }
        conf = {"name": 0.95, "aadhaar_number": 0.98}
        res = self.router.evaluate_routing(
            document_type="aadhaar",
            confidence=0.96,
            fields=fields,
            field_confidence=conf,
            warnings=[],
        )
        assert res.success is True
        assert res.data.status == "PASS"
        assert res.data.risk_score < 0.1

    def test_routing_fail_on_invalid_pan(self):
        """Test invalid PAN routes to FAIL"""
        fields = {"name": "Test User", "pan_number": "INVALID"}
        conf = {"name": 0.9, "pan_number": 0.9}
        res = self.router.evaluate_routing(
            document_type="pan",
            confidence=0.92,
            fields=fields,
            field_confidence=conf,
            warnings=["pan_format_invalid"],
        )
        assert res.success is True
        assert res.data.status == "FAIL"
        assert res.data.risk_score > 0.8

    def test_routing_manual_review_on_low_scan_quality(self):
        """Test blurry scan routes to MANUAL REVIEW"""
        fields = {"name": "Priya Sharma", "aadhaar_number": "XXXX XXXX 1234"}
        conf = {"name": 0.6, "aadhaar_number": 0.6}
        res = self.router.evaluate_routing(
            document_type="aadhaar",
            confidence=0.65,
            fields=fields,
            field_confidence=conf,
            warnings=["low_scan_quality_overall"],
        )
        assert res.success is True
        assert res.data.status == "MANUAL_REVIEW"

    def test_database_persistence_and_stats(self):
        """Test saving verification record and retrieving stats from SQLite"""
        rec_id = f"test_{os.urandom(4).hex()}"
        record = {
            "verification_id": rec_id,
            "document_type": "aadhaar",
            "filename": "test_aadhaar.png",
            "file_type": "image/png",
            "file_size_bytes": 1024,
            "confidence": 0.95,
            "routing_status": "PASS",
            "routing_reasons": ["All integrity checks passed"],
            "extracted_fields": {"name": "Shriyansh Gupta"},
            "masked_fields": {"name": "Shriyansh Gupta", "aadhaar_number": "XXXX XXXX 1234"},
            "field_level_scores": {"name": 0.95},
            "warnings": [],
            "masked": True,
            "processing_time_ms": 120.5,
        }
        audit = [
            {
                "stage_name": "Ingestion",
                "status": "SUCCESS",
                "execution_time_ms": 15.2,
                "input_summary": "Test image",
                "output_summary": "Parsed text",
                "details": {},
            }
        ]

        saved_id = save_verification_record(record, audit)
        assert saved_id == rec_id

        fetched = get_verification_record(rec_id)
        assert fetched is not None
        assert fetched["routing_status"] == "PASS"
        assert len(fetched["audit_logs"]) == 1

        stats = get_verification_stats()
        assert stats["total_processed"] >= 1
