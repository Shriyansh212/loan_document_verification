"""
Orchestrator Agent - Coordinates the end-to-end multi-stage pipeline,
tracks stage latency, records audit logs, runs automated routing, and persists to SQLite.
"""

import asyncio
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from models.schemas import (
    ProcessingResult,
    RoutingResult,
    StageAuditLogSchema,
    AgentResponse,
)
from agents.ingestion import IngestionAgent
from agents.classifier import ClassifierAgent
from agents.extractor import ExtractorAgent
from agents.validator import ValidatorAgent
from agents.masker import MaskerAgent
from agents.router import RoutingAgent
from agents.aggregator import AggregatorAgent
from database.crud import (
    save_verification_record,
    get_verification_record,
    list_verification_records,
    get_stage_audit_logs,
    get_verification_stats,
)
from utils.logger import get_logger, setup_pii_redaction

logger = get_logger(__name__)
setup_pii_redaction()

router = APIRouter()


class OrchestratorAgent:
    """
    Multi-stage Pipeline Orchestrator
    
    Coordinates:
    Orchestrator → Ingestion → [PDF Text | OCR Engine]
                 → Classifier → Extractor (Groq Llama)
                 → [Validator ‖ Masker] (parallel)
                 → Automated Routing (PASS / FAIL / MANUAL REVIEW)
                 → Aggregator → SQL Database Storage & Stage Audit Logs
    """

    def __init__(self):
        self.ingestion_agent = IngestionAgent()
        self.classifier_agent = ClassifierAgent()
        self.extractor_agent = ExtractorAgent()
        self.validator_agent = ValidatorAgent()
        self.masker_agent = MaskerAgent()
        self.routing_agent = RoutingAgent()
        self.aggregator_agent = AggregatorAgent()

    async def process_document(
        self,
        file: Optional[UploadFile] = None,
        raw_text_override: Optional[str] = None,
        sample_doc_type: Optional[str] = None,
        filename_override: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Executes the multi-stage document verification pipeline.
        Records execution time for every stage and logs audit records.
        """
        overall_start = time.perf_counter()
        verification_id = f"verif_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        audit_trail: List[StageAuditLogSchema] = []

        filename = filename_override or (file.filename if file else "sample_document.txt")
        file_type = file.content_type if file else "text/plain"
        file_size = 0

        logger.info(f"[{verification_id}] Starting verification pipeline for: {filename}")

        # ----------------------------------------------------
        # STAGE 1: Ingestion & Text Extraction
        # ----------------------------------------------------
        stage1_start = time.perf_counter()
        raw_text = ""
        processing_path = "direct_text"

        try:
            if raw_text_override:
                raw_text = raw_text_override
                file_size = len(raw_text.encode("utf-8"))
                processing_path = "sample_loader"
            elif file:
                file_content = await file.read()
                file_size = len(file_content)
                await file.seek(0)

                ingestion_result = await self.ingestion_agent.process_file(file)
                if not ingestion_result.success:
                    raise Exception(f"Ingestion failed: {ingestion_result.error}")
                raw_text = ingestion_result.data.raw_text
                processing_path = ingestion_result.data.processing_path

            stage1_latency = (time.perf_counter() - stage1_start) * 1000
            audit_trail.append(
                StageAuditLogSchema(
                    stage_name="Ingestion & Extraction",
                    status="SUCCESS",
                    execution_time_ms=round(stage1_latency, 2),
                    input_summary=f"File: {filename} ({file_size} bytes, type: {file_type})",
                    output_summary=f"Extracted {len(raw_text)} chars via {processing_path}",
                    details={"path": processing_path, "char_count": len(raw_text)},
                )
            )
        except Exception as e:
            stage1_latency = (time.perf_counter() - stage1_start) * 1000
            audit_trail.append(
                StageAuditLogSchema(
                    stage_name="Ingestion & Extraction",
                    status="ERROR",
                    execution_time_ms=round(stage1_latency, 2),
                    input_summary=f"File: {filename}",
                    output_summary=f"Error: {str(e)}",
                    details={"error": str(e)},
                )
            )
            raise HTTPException(status_code=400, detail=f"Ingestion stage failed: {e}")

        # ----------------------------------------------------
        # STAGE 2: Classification (Fuzzy + LLM)
        # ----------------------------------------------------
        stage2_start = time.perf_counter()
        classifier_result = await self.classifier_agent.classify_document(raw_text)
        stage2_latency = (time.perf_counter() - stage2_start) * 1000

        doc_type = None
        confidence = 0.0

        if classifier_result.success and classifier_result.data:
            doc_type = classifier_result.data.document_type
            confidence = classifier_result.data.confidence
            audit_trail.append(
                StageAuditLogSchema(
                    stage_name="Document Classification",
                    status="SUCCESS",
                    execution_time_ms=round(stage2_latency, 2),
                    input_summary=f"OCR Text sample: {raw_text[:120].strip()}...",
                    output_summary=f"Classified as '{doc_type}' with {confidence:.1%} confidence",
                    details={"doc_type": doc_type, "confidence": confidence},
                )
            )
        else:
            audit_trail.append(
                StageAuditLogSchema(
                    stage_name="Document Classification",
                    status="WARNING",
                    execution_time_ms=round(stage2_latency, 2),
                    input_summary=f"OCR Text length: {len(raw_text)}",
                    output_summary="Failed to classify document into supported Indian ID types",
                    details={"error": classifier_result.error},
                )
            )

        # If document could not be classified, route directly to FAIL
        if not doc_type:
            total_time_ms = (time.perf_counter() - overall_start) * 1000
            routing_res = RoutingResult(
                status="FAIL",
                reasons=["Document not recognized as supported Indian ID (Aadhaar, PAN, Voter ID, DL, Passport)"],
                risk_score=1.0,
                review_flags=["unsupported_document_type"],
                compliance_checks={"document_recognized": False},
            )
            fail_result = ProcessingResult(
                verification_id=verification_id,
                document_type=None,
                confidence=0.0,
                routing_status="FAIL",
                routing_reasons=routing_res.reasons,
                fields={},
                masked=False,
                field_level_scores={},
                extraction_warnings=["unsupported_document_type"],
                compliance_checks=routing_res.compliance_checks,
                risk_score=1.0,
                processing_time_ms=round(total_time_ms, 2),
                audit_trail=audit_trail,
                error="unsupported_document_type",
                error_detail="Document could not be classified as one of the five supported types.",
            )
            # Save to SQLite
            self._save_to_database(fail_result, filename, file_type, file_size, audit_trail)
            return fail_result

        # ----------------------------------------------------
        # STAGE 3: Structured Field Extraction (Groq Llama)
        # ----------------------------------------------------
        stage3_start = time.perf_counter()
        extractor_result = await self.extractor_agent.extract_fields(raw_text, doc_type)
        stage3_latency = (time.perf_counter() - stage3_start) * 1000

        if not extractor_result.success or not extractor_result.data:
            audit_trail.append(
                StageAuditLogSchema(
                    stage_name="LLM Field Extraction",
                    status="ERROR",
                    execution_time_ms=round(stage3_latency, 2),
                    input_summary=f"Doc type: {doc_type}",
                    output_summary=f"Extraction failed: {extractor_result.error}",
                    details={"error": extractor_result.error},
                )
            )
            raise HTTPException(status_code=500, detail=f"Extraction stage failed: {extractor_result.error}")

        extracted_fields = extractor_result.data.fields
        field_confidence = extractor_result.data.field_confidence
        audit_trail.append(
            StageAuditLogSchema(
                stage_name="LLM Field Extraction",
                status="SUCCESS",
                execution_time_ms=round(stage3_latency, 2),
                input_summary=f"Groq Llama 3.3 schema-guided extraction for '{doc_type}'",
                output_summary=f"Extracted {len(extracted_fields)} structured fields",
                details={"field_count": len(extracted_fields), "fields": list(extracted_fields.keys())},
            )
        )

        # ----------------------------------------------------
        # STAGE 4: Parallel Validation & PII Masking
        # ----------------------------------------------------
        stage4_start = time.perf_counter()
        validator_task = self.validator_agent.validate_fields(extracted_fields, doc_type)
        masker_task = self.masker_agent.mask_fields(extracted_fields, doc_type)

        validator_result, masker_result = await asyncio.gather(
            validator_task,
            masker_task,
            return_exceptions=True,
        )
        stage4_latency = (time.perf_counter() - stage4_start) * 1000

        if isinstance(validator_result, Exception):
            raise HTTPException(status_code=500, detail=f"Validation failed: {str(validator_result)}")
        if isinstance(masker_result, Exception):
            raise HTTPException(status_code=500, detail=f"Masking failed: {str(masker_result)}")

        val_warnings = validator_result.data.warnings if validator_result.data else []
        masking_done = masker_result.data.masking_applied if masker_result.data else False

        audit_trail.append(
            StageAuditLogSchema(
                stage_name="Validation & Security Masking",
                status="WARNING" if val_warnings else "SUCCESS",
                execution_time_ms=round(stage4_latency, 2),
                input_summary=f"Parallel verification of {len(extracted_fields)} fields",
                output_summary=f"Masking applied: {masking_done}, Warnings generated: {len(val_warnings)}",
                details={"warnings": val_warnings, "masked": masking_done},
            )
        )

        # ----------------------------------------------------
        # STAGE 5: Automated Routing Engine (PASS, FAIL, MANUAL REVIEW)
        # ----------------------------------------------------
        stage5_start = time.perf_counter()
        routing_response = self.routing_agent.evaluate_routing(
            document_type=doc_type,
            confidence=confidence,
            fields=extracted_fields,
            field_confidence=field_confidence,
            warnings=val_warnings,
        )
        stage5_latency = (time.perf_counter() - stage5_start) * 1000

        routing_result = routing_response.data
        audit_trail.append(
            StageAuditLogSchema(
                stage_name="Automated Routing Decision",
                status="SUCCESS" if routing_result.status == "PASS" else ("WARNING" if routing_result.status == "MANUAL_REVIEW" else "ERROR"),
                execution_time_ms=round(stage5_latency, 2),
                input_summary=f"Risk Score: {routing_result.risk_score:.2f}, Warnings: {len(val_warnings)}",
                output_summary=f"Decision: {routing_result.status} ({len(routing_result.reasons)} policy criteria)",
                details={"status": routing_result.status, "reasons": routing_result.reasons},
            )
        )

        # ----------------------------------------------------
        # STAGE 6: Aggregation & Final JSON Serialization
        # ----------------------------------------------------
        total_time_ms = (time.perf_counter() - overall_start) * 1000

        aggregator_response = await self.aggregator_agent.aggregate_results(
            verification_id=verification_id,
            doc_type=doc_type,
            confidence=confidence,
            field_confidence=field_confidence,
            validator_result=validator_result.data,
            masker_result=masker_result.data,
            routing_result=routing_result,
            total_time_ms=total_time_ms,
            audit_trail=audit_trail,
        )

        if not aggregator_response.success:
            raise HTTPException(status_code=500, detail=aggregator_response.error)

        final_result = aggregator_response.data

        # ----------------------------------------------------
        # STAGE 7: SQLite Result Storage & Stage Audit Logs
        # ----------------------------------------------------
        self._save_to_database(final_result, filename, file_type, file_size, audit_trail)

        return final_result

    def _save_to_database(
        self,
        result: ProcessingResult,
        filename: str,
        file_type: str,
        file_size: int,
        audit_trail: List[StageAuditLogSchema],
    ):
        """Helper to safely store verification record and audit trail in SQLite."""
        try:
            record_dict = {
                "verification_id": result.verification_id,
                "document_type": result.document_type,
                "filename": filename,
                "file_type": file_type,
                "file_size_bytes": file_size,
                "confidence": result.confidence,
                "routing_status": result.routing_status,
                "routing_reasons": result.routing_reasons,
                "extracted_fields": result.fields,
                "masked_fields": result.fields,
                "field_level_scores": result.field_level_scores,
                "warnings": result.extraction_warnings,
                "masked": result.masked,
                "processing_time_ms": result.processing_time_ms,
            }
            audit_dicts = [a.model_dump() for a in audit_trail]
            save_verification_record(record_dict, audit_dicts)
            logger.info(f"Saved verification {result.verification_id} to SQLite database.")
        except Exception as e:
            logger.error(f"Failed to persist verification record to SQLite: {e}")


# Global orchestrator instance
orchestrator = OrchestratorAgent()


@router.post("/process", response_model=ProcessingResult)
async def process_kyc_document(
    file: UploadFile = File(..., description="Document file (PDF, PNG, JPEG, TIFF)"),
) -> ProcessingResult:
    """
    Process an uploaded identity document through the multi-stage pipeline.
    """
    allowed_types = ["application/pdf", "image/png", "image/jpeg", "image/jpg", "image/tiff", "image/tif"]
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}

    ext = os.path.splitext(file.filename or "")[1].lower()
    if file.content_type not in allowed_types and ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Supported: PDF, PNG, JPG, TIFF",
        )

    # 10 MB limit
    max_size = 10 * 1024 * 1024
    content = await file.read()
    await file.seek(0)
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {len(content)/1024/1024:.2f}MB (maximum 10MB)",
        )

    return await orchestrator.process_document(file=file)


@router.post("/sample/{sample_key}", response_model=ProcessingResult)
async def process_sample_document(sample_key: str) -> ProcessingResult:
    """
    Instant 1-click verification of built-in sample identity documents.
    Ideal for recruiters, live demos, and integration testing without needing physical IDs!
    """
    samples = {
        "aadhaar_pass": {
            "name": "sample_aadhaar_clean.png",
            "text": "GOVERNMENT OF INDIA\nUNIQUE IDENTIFICATION AUTHORITY OF INDIA\n\nTo,\nShriyansh Gupta\nDOB: 1998-05-14\nGender: Male / पुरुष\n\nAddress: 42 Silicon Enclave, Indiranagar, Bengaluru, Karnataka 560038\n\n9841 2356 7192\nमेरा आधार, मेरी पहचान",
        },
        "pan_pass": {
            "name": "sample_pan_card.jpg",
            "text": "INCOME TAX DEPARTMENT\nGOVT. OF INDIA\n\nPERMANENT ACCOUNT NUMBER\nABCDE1234F\n\nName: SHRIYANSH GUPTA\nFather's Name: RAJESH GUPTA\nDate of Birth: 1998-05-14",
        },
        "voter_pass": {
            "name": "sample_voter_id.jpg",
            "text": "ELECTION COMMISSION OF INDIA\nELECTOR PHOTO IDENTITY CARD\n\nEPIC No: WXH1293847\nName: SHRIYANSH GUPTA\nFather's Name: RAJESH GUPTA\nGender: Male\nDOB: 1998-05-14\nConstituency: Bangalore South",
        },
        "passport_pass": {
            "name": "sample_passport.jpg",
            "text": "PASSPORT\nREPUBLIC OF INDIA\nType: P  Country Code: IND  Passport No: Z9182736\nName: GUPTA SHRIYANSH\nNationality: IND\nSex: M\nDate of Birth: 1998-05-14\nExpiry Date: 2032-05-13\n\nP<INDGUPTA<<SHRIYANSH<<<<<<<<<<<<<<<<<<<<<<<\nZ9182736<2IND9805146M3205138<<<<<<<<<<<<<<4",
        },
        "blurry_review": {
            "name": "sample_blurry_scan.png",
            "text": "GOVERNMENT OF INDIA\nUIDAI AADHAAR\nName: S. Gupta\nDOB: 1998-05-14\nGender: M\nAddress: [unreadable ink smudge 560038]\nAadhaar: 9841 2356 7192",
        },
        "invalid_fail": {
            "name": "sample_forged_pan.jpg",
            "text": "INCOME TAX DEPARTMENT\nPERMANENT ACCOUNT NUMBER\n999INVALID-PAN\nName: Unknown User\nDOB: 2050-01-01",
        },
    }

    if sample_key not in samples:
        raise HTTPException(
            status_code=404,
            detail=f"Sample '{sample_key}' not found. Available: {', '.join(samples.keys())}",
        )

    sample = samples[sample_key]
    return await orchestrator.process_document(
        raw_text_override=sample["text"],
        filename_override=sample["name"],
    )


@router.get("/records")
async def list_records(
    status: Optional[str] = Query(None, description="Filter by status: PASS, FAIL, MANUAL_REVIEW, or ALL"),
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List past verification records from SQLite database with filtering and pagination.
    """
    return list_verification_records(status_filter=status, doc_type_filter=doc_type, limit=limit, offset=offset)


@router.get("/records/{verification_id}")
async def get_record(verification_id: str):
    """
    Retrieve complete verification record and stage audit logs.
    """
    record = get_verification_record(verification_id)
    if not record:
        raise HTTPException(status_code=404, detail="Verification record not found")
    return record


@router.get("/records/{verification_id}/audit")
async def get_record_audit_logs(verification_id: str):
    """
    Retrieve stage-by-stage audit trail for traceability and debugging.
    """
    return get_stage_audit_logs(verification_id)


@router.get("/stats")
async def get_analytics():
    """
    Retrieve aggregate statistics across all verification pipeline runs.
    """
    return get_verification_stats()
