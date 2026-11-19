"""
Database data models for verification records and stage audit logs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class VerificationRecord:
    verification_id: str
    document_type: Optional[str]
    filename: Optional[str]
    file_type: Optional[str]
    file_size_bytes: int
    confidence: float
    routing_status: str  # PASS, FAIL, MANUAL_REVIEW
    routing_reasons: List[str] = field(default_factory=list)
    extracted_fields: Dict[str, Any] = field(default_factory=dict)
    masked_fields: Dict[str, Any] = field(default_factory=dict)
    field_level_scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    masked: bool = False
    processing_time_ms: float = 0.0
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class StageAuditLog:
    verification_id: str
    stage_name: str
    status: str  # SUCCESS, WARNING, ERROR
    execution_time_ms: float = 0.0
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    id: Optional[int] = None
    created_at: Optional[str] = None
