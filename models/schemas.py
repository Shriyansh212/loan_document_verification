"""
Pydantic models for KYC document schemas, automated routing, and audit logs.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field


class FieldConfidence(BaseModel):
    """Field-level confidence scores"""
    name: Optional[float] = None
    dob: Optional[float] = None
    gender: Optional[float] = None
    address: Optional[float] = None
    aadhaar_number: Optional[float] = None
    fathers_name: Optional[float] = None
    pan_number: Optional[float] = None
    relative_name: Optional[float] = None
    voter_id_number: Optional[float] = None
    constituency: Optional[float] = None
    dl_number: Optional[float] = None
    valid_from: Optional[float] = None
    valid_until: Optional[float] = None
    vehicle_classes: Optional[float] = None
    passport_number: Optional[float] = None
    nationality: Optional[float] = None
    expiry_date: Optional[float] = None
    mrz_line: Optional[float] = None


class AadhaarFields(BaseModel):
    """Aadhaar Card fields"""
    name: Optional[str] = None
    fathers_name: Optional[str] = Field(None, description="Father's name or Care Of (S/O, C/O)")
    dob: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    gender: Optional[Literal["M", "F", "O"]] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = Field(None, description="12-digit Aadhaar number, will be masked")


class PANFields(BaseModel):
    """PAN Card fields"""
    name: Optional[str] = None
    fathers_name: Optional[str] = None
    dob: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    pan_number: Optional[str] = Field(None, pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class VoterIDFields(BaseModel):
    """Voter ID fields"""
    name: Optional[str] = None
    relative_name: Optional[str] = Field(None, description="Father's or Husband's name")
    dob: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    voter_id_number: Optional[str] = None
    address: Optional[str] = None
    constituency: Optional[str] = None


class DrivingLicenceFields(BaseModel):
    """Driving Licence fields"""
    name: Optional[str] = None
    dob: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    dl_number: Optional[str] = None
    valid_from: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    valid_until: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    vehicle_classes: Optional[List[str]] = Field(default_factory=list)
    address: Optional[str] = None


class PassportFields(BaseModel):
    """Passport fields"""
    name: Optional[str] = None
    dob: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    passport_number: Optional[str] = None
    nationality: Optional[str] = Field(None, description="3-letter ISO country code")
    expiry_date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    mrz_line: Optional[str] = Field(None, description="Full MRZ string")


DocumentFields = Union[AadhaarFields, PANFields, VoterIDFields, DrivingLicenceFields, PassportFields]


class ClassifierResult(BaseModel):
    """Result from document classifier"""
    document_type: Optional[Literal["aadhaar", "pan", "voter_id", "driving_licence", "passport"]] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class ExtractorResult(BaseModel):
    """Result from field extractor"""
    fields: Dict[str, Any] = Field(default_factory=dict)
    field_confidence: Dict[str, float] = Field(default_factory=dict)


class ValidatorResult(BaseModel):
    """Result from field validator"""
    warnings: List[str] = Field(default_factory=list)
    is_valid: bool = True


class MaskerResult(BaseModel):
    """Result from field masker"""
    masked_fields: Dict[str, Any] = Field(default_factory=dict)
    masking_applied: bool = False


class RoutingResult(BaseModel):
    """Result from automated routing decision engine"""
    status: Literal["PASS", "FAIL", "MANUAL_REVIEW"]
    reasons: List[str] = Field(default_factory=list)
    risk_score: float = Field(0.0, ge=0.0, le=1.0)
    review_flags: List[str] = Field(default_factory=list)
    compliance_checks: Dict[str, bool] = Field(default_factory=dict)


class StageAuditLogSchema(BaseModel):
    """Audit entry for each pipeline stage"""
    stage_name: str
    status: Literal["SUCCESS", "WARNING", "ERROR"]
    execution_time_ms: float
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    """Final processing result with automated routing and audit traceability"""
    verification_id: Optional[str] = None
    document_type: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    routing_status: Literal["PASS", "FAIL", "MANUAL_REVIEW"] = "MANUAL_REVIEW"
    routing_reasons: List[str] = Field(default_factory=list)
    fields: Dict[str, Any] = Field(default_factory=dict)
    masked: bool = False
    field_level_scores: Dict[str, float] = Field(default_factory=dict)
    extraction_warnings: List[str] = Field(default_factory=list)
    compliance_checks: Dict[str, bool] = Field(default_factory=dict)
    risk_score: float = Field(0.0, ge=0.0, le=1.0)
    processing_time_ms: float = 0.0
    audit_trail: List[StageAuditLogSchema] = Field(default_factory=list)
    error: Optional[str] = None
    error_detail: Optional[str] = None


class IngestionResult(BaseModel):
    """Result from ingestion agent"""
    raw_text: str
    processing_path: Literal["pdf_text", "ocr"]
    file_type: str


class AgentResponse(BaseModel):
    """Generic agent response wrapper"""
    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


SUPPORTED_DOCUMENT_TYPES = {
    "aadhaar": AadhaarFields,
    "pan": PANFields,
    "voter_id": VoterIDFields,
    "driving_licence": DrivingLicenceFields,
    "passport": PassportFields,
}



class CrossDocumentConsistency(BaseModel):
    """Cross-document identity consistency validation result"""
    name_match: bool = True
    name_similarity: float = 1.0
    name_doc1: Optional[str] = None
    name_doc2: Optional[str] = None
    fathers_name_match: bool = True
    fathers_name_doc1: Optional[str] = None
    fathers_name_doc2: Optional[str] = None
    gender_match: bool = True
    gender_doc1: Optional[str] = None
    gender_doc2: Optional[str] = None
    dob_match: bool = True
    dob_doc1: Optional[str] = None
    dob_doc2: Optional[str] = None
    cross_warnings: List[str] = Field(default_factory=list)
    mismatch_details: List[str] = Field(default_factory=list)


class MultiDocumentVerificationResult(BaseModel):
    """Result for Loan KYC and multi-document verification with cross-validation"""
    batch_id: str
    overall_routing_status: Literal["PASS", "FAIL", "MANUAL_REVIEW"]
    cross_match_score: float = 1.0
    overall_reasons: List[str] = Field(default_factory=list)
    cross_consistency: CrossDocumentConsistency = Field(default_factory=CrossDocumentConsistency)
    documents: List[ProcessingResult] = Field(default_factory=list)
    total_processing_time_ms: float = 0.0
