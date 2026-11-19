"""
Aggregator Agent - Merges validator warnings, masked fields, routing decisions,
and audit logs into final response.
"""

from typing import Any, Dict, List, Optional
from models.schemas import (
    ProcessingResult,
    ValidatorResult,
    MaskerResult,
    RoutingResult,
    StageAuditLogSchema,
    AgentResponse,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class AggregatorAgent:
    """
    Aggregator Agent - Combines all agent results into the final unified response.
    
    Merges:
    - Document classification & confidence
    - Masked structured fields (ensuring zero unmasked Aadhaar leakage)
    - Field-level confidence scores
    - Validation warnings & integrity flags
    - Automated Routing decision (PASS, FAIL, MANUAL_REVIEW)
    - Stage-by-stage audit trail with latency profiling
    """

    def __init__(self):
        self.name = "Aggregator Agent"

    async def aggregate_results(
        self,
        verification_id: str,
        doc_type: Optional[str],
        confidence: float,
        field_confidence: Dict[str, float],
        validator_result: ValidatorResult,
        masker_result: MaskerResult,
        routing_result: RoutingResult,
        total_time_ms: float,
        audit_trail: List[StageAuditLogSchema],
    ) -> AgentResponse:
        """
        Aggregate all processing results into final ProcessingResult.
        """
        try:
            logger.info("Starting result aggregation...")

            # Build final response
            final_result = ProcessingResult(
                verification_id=verification_id,
                document_type=doc_type,
                confidence=confidence,
                routing_status=routing_result.status,
                routing_reasons=routing_result.reasons,
                fields=masker_result.masked_fields,
                masked=masker_result.masking_applied,
                field_level_scores=field_confidence,
                extraction_warnings=validator_result.warnings,
                compliance_checks=routing_result.compliance_checks,
                risk_score=routing_result.risk_score,
                processing_time_ms=round(total_time_ms, 2),
                audit_trail=audit_trail,
                error=None,
                error_detail=None,
            )

            # Security sanity check: Ensure no unmasked 12-digit Aadhaar number escapes
            if not self._validate_response_security(final_result):
                logger.error("Security validation failed - unmasked sensitive data detected!")
                return AgentResponse(
                    success=False,
                    error="Response security validation failed: unmasked PII detected",
                )

            logger.info(f"Aggregation completed for {verification_id} -> Status: {routing_result.status}")

            return AgentResponse(
                success=True,
                data=final_result,
            )

        except Exception as e:
            logger.error(f"Error in result aggregation: {e}")
            return AgentResponse(
                success=False,
                error=f"Aggregation failed: {e}",
            )

    def _validate_response_security(self, result: ProcessingResult) -> bool:
        """
        Ensure unmasked Aadhaar numbers never appear in output.
        """
        try:
            if result.document_type == "aadhaar":
                num = result.fields.get("aadhaar_number", "")
                if num and not str(num).startswith("XXXX"):
                    return False
            return True
        except Exception:
            return False
