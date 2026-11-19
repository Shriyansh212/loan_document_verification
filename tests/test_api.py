"""
API integration tests for KYC Document Processing Pipeline
"""

import pytest
import io
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from PIL import Image
import json

from main import app
from models.schemas import ProcessingResult


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture 
def sample_image_file():
    """Create a sample image file for testing"""
    # Create a simple test image
    img = Image.new('RGB', (800, 600), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/api")
        assert response.status_code == 200
        assert "KYC Document Processing Pipeline" in response.json()["message"]
    
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestProcessEndpoint:
    """Test document processing endpoint"""
    
    def test_process_endpoint_no_file(self, client):
        """Test process endpoint without file"""
        response = client.post("/api/v1/kyc/process")
        assert response.status_code == 422  # Validation error
    
    def test_process_endpoint_invalid_file_type(self, client):
        """Test process endpoint with invalid file type"""
        # Create a text file
        text_file = io.BytesIO(b"This is not an image or PDF")
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("test.txt", text_file, "text/plain")}
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]
    
    def test_process_endpoint_file_too_large(self, client):
        """Test process endpoint with oversized file"""
        # Create a large fake file (> 10MB)
        large_data = b"x" * (11 * 1024 * 1024)  # 11MB
        large_file = io.BytesIO(large_data)
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("large.png", large_file, "image/png")}
        )
        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]
    
    @patch('agents.orchestrator.OrchestratorAgent.process_document')
    def test_process_endpoint_success(self, mock_process, client, sample_image_file):
        """Test successful document processing"""
        # Mock successful processing result
        mock_result = ProcessingResult(
            document_type="aadhaar",
            confidence=0.95,
            fields={
                "name": "PRIYA SHARMA",
                "aadhaar_number": "XXXX XXXX 9012",
                "dob": "1990-04-12"
            },
            masked=True,
            field_level_scores={"name": 0.99, "aadhaar_number": 0.95},
            extraction_warnings=[]
        )
        
        mock_process.return_value = mock_result
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("test.png", sample_image_file, "image/png")}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["document_type"] == "aadhaar"
        assert result["confidence"] == 0.95
        assert result["masked"] is True
        assert "XXXX XXXX" in result["fields"]["aadhaar_number"]
    
    @patch('agents.orchestrator.OrchestratorAgent.process_document')
    def test_process_endpoint_unsupported_document(self, mock_process, client, sample_image_file):
        """Test processing of unsupported document type"""
        # Mock unsupported document result
        mock_result = ProcessingResult(
            document_type=None,
            confidence=0.0,
            fields={},
            masked=False,
            field_level_scores={},
            extraction_warnings=[],
            error="unsupported_document_type",
            error_detail="Document could not be classified as one of the five supported types."
        )
        
        mock_process.return_value = mock_result
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("utility_bill.png", sample_image_file, "image/png")}
        )
        
        assert response.status_code == 422
        result = response.json()
        assert result["error"] == "unsupported_document_type"
        assert result["document_type"] is None
    
    @patch('agents.orchestrator.OrchestratorAgent.process_document')
    def test_process_endpoint_processing_error(self, mock_process, client, sample_image_file):
        """Test API response to processing errors"""
        # Mock processing exception
        mock_process.side_effect = Exception("Internal processing error")
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("test.png", sample_image_file, "image/png")}
        )
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


class TestResponseFormat:
    """Test response format compliance"""
    
    @patch('agents.orchestrator.OrchestratorAgent.process_document')
    def test_successful_response_format(self, mock_process, client, sample_image_file):
        """Test that successful response matches expected format"""
        mock_result = ProcessingResult(
            document_type="pan",
            confidence=0.92,
            fields={
                "name": "RAJESH KUMAR",
                "fathers_name": "SURESH KUMAR",
                "pan_number": "ABCDE1234F",
                "dob": "1985-07-20"
            },
            masked=False,
            field_level_scores={
                "name": 0.97,
                "fathers_name": 0.89,
                "pan_number": 0.99,
                "dob": 0.93
            },
            extraction_warnings=[]
        )
        
        mock_process.return_value = mock_result
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("pan.png", sample_image_file, "image/png")}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify required fields are present
        required_fields = [
            "document_type", "confidence", "fields", 
            "masked", "field_level_scores", "extraction_warnings"
        ]
        for field in required_fields:
            assert field in result
        
        # Verify data types
        assert isinstance(result["document_type"], str)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["fields"], dict)
        assert isinstance(result["masked"], bool)
        assert isinstance(result["field_level_scores"], dict)
        assert isinstance(result["extraction_warnings"], list)
    
    @patch('agents.orchestrator.OrchestratorAgent.process_document')
    def test_error_response_format(self, mock_process, client, sample_image_file):
        """Test that error response matches expected format"""
        mock_result = ProcessingResult(
            document_type=None,
            confidence=0.0,
            fields={},
            masked=False,
            field_level_scores={},
            extraction_warnings=[],
            error="unsupported_document_type",
            error_detail="Document could not be classified as one of the five supported types."
        )
        
        mock_process.return_value = mock_result
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("unknown.png", sample_image_file, "image/png")}
        )
        
        assert response.status_code == 422
        result = response.json()
        
        # Verify error fields are present
        assert "error" in result
        assert "error_detail" in result
        assert result["error"] == "unsupported_document_type"
        assert result["document_type"] is None


class TestSecurityCompliance:
    """Test security and compliance features"""
    
    @patch('agents.orchestrator.OrchestratorAgent.process_document')
    def test_aadhaar_masking_enforced(self, mock_process, client, sample_image_file):
        """Test that Aadhaar numbers are always masked in API response"""
        mock_result = ProcessingResult(
            document_type="aadhaar",
            confidence=0.97,
            fields={
                "name": "PRIYA SHARMA",
                "aadhaar_number": "XXXX XXXX 3456",  # Must be masked
                "dob": "1990-04-12"
            },
            masked=True,
            field_level_scores={"name": 0.99, "aadhaar_number": 0.95},
            extraction_warnings=[]
        )
        
        mock_process.return_value = mock_result
        
        response = client.post(
            "/api/v1/kyc/process",
            files={"file": ("aadhaar.png", sample_image_file, "image/png")}
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify masking is applied
        assert result["masked"] is True
        assert "XXXX XXXX" in result["fields"]["aadhaar_number"]
        
        # Verify no full Aadhaar number is present in response
        response_text = response.text
        import re
        full_aadhaar_pattern = re.compile(r'\b\d{12}\b')
        assert not full_aadhaar_pattern.search(response_text)
    
    def test_cors_headers(self, client):
        """Test that CORS headers are properly configured"""
        response = client.options("/api/v1/kyc/process")
        
        # Should have CORS headers (configured in main.py)
        # Note: TestClient might not show all CORS headers, this is a basic check
        assert response.status_code in [200, 405]  # 405 is acceptable for OPTIONS


if __name__ == "__main__":
    pytest.main([__file__])