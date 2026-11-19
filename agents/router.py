"""
Routing Agent - Automated decision engine for document verification.
Implements multi-stage validation checks, cross-field consistency verification,
and automated routing to PASS, FAIL, or MANUAL REVIEW.
"""

from typing import Any, Dict, List, Optional
from models.schemas import AgentResponse, RoutingResult
from utils.logger import get_logger

logger = get_logger(__name__)


class RoutingAgent:
    """
    Automated Routing Engine
    
    Evaluates extraction quality, schema validation warnings, checksums,
    and cross-field consistency to determine final verification status:
    - PASS: All mandatory fields present, checksums valid, high confidence.
    - FAIL: Critical validation failure (checksum mismatch, expired ID, invalid format).
    - MANUAL_REVIEW: Scan quality low, minor warnings, borderline confidence.
    """

    MANDATORY_FIELDS = {
        "aadhaar": ["name", "aadhaar_number"],
        "pan": ["name", "pan_number"],
        "voter_id": ["name", "voter_id_number"],
        "driving_licence": ["name", "dl_number", "valid_until"],
        "passport": ["name", "passport_number", "expiry_date"],
    }

    CRITICAL_FAIL_WARNINGS = {
        "aadhaar_luhn_failed": "Aadhaar Luhn checksum verification failed (invalid ID number)",
        "aadhaar_invalid_length": "Aadhaar number length is invalid (must be 12 digits)",
        "pan_format_invalid": "PAN format violation (must match 5 letters, 4 digits, 1 letter)",
        "dl_expired": "Driving Licence is expired and invalid for active verification",
        "mrz_checksum_failed": "Passport MRZ check digit checksum failed (possible tampering)",
        "mrz_passport_number_mismatch": "Cross-field mismatch between visual passport number and MRZ line",
    }

    MANUAL_REVIEW_WARNINGS = {
        "low_scan_quality_overall": "Document scan resolution or contrast is low",
        "name_too_short": "Extracted name contains fewer than 2 characters (possible OCR truncation)",
        "aadhaar_invalid_gender": "Gender value does not conform to standard M/F/O",
        "dl_invalid_date_range": "Driving licence issue date appears after validity date",
        "mrz_validation_failed": "Passport MRZ parsing encountered format irregularities",
    }

    def __init__(self):
        self.name = "Routing Agent"
        self.min_pass_confidence = 0.75
        self.critical_field_min_confidence = 0.65

    def evaluate_routing(
        self,
        document_type: Optional[str],
        confidence: float,
        fields: Dict[str, Any],
        field_confidence: Dict[str, float],
        warnings: List[str],
    ) -> AgentResponse:
        """
        Evaluate verification criteria and assign routing status.
        """
        try:
            reasons: List[str] = []
            review_flags: List[str] = []
            compliance_checks: Dict[str, bool] = {
                "document_recognized": bool(document_type),
                "mandatory_fields_present": True,
                "checksums_verified": True,
                "document_active": True,
                "scan_quality_acceptable": True,
                "cross_field_consistent": True,
            }

            # 1. Check document type recognition
            if not document_type or document_type == "unknown":
                compliance_checks["document_recognized"] = False
                return AgentResponse(
                    success=True,
                    data=RoutingResult(
                        status="FAIL",
                        reasons=["Unsupported or unidentifiable document type"],
                        risk_score=1.0,
                        review_flags=["unsupported_document_type"],
                        compliance_checks=compliance_checks,
                    ),
                )

            # 2. Check for critical failure warnings
            fail_reasons = []
            for w in warnings:
                if w in self.CRITICAL_FAIL_WARNINGS:
                    fail_reasons.append(self.CRITICAL_FAIL_WARNINGS[w])
                    compliance_checks["checksums_verified"] = False
                    if "expired" in w:
                        compliance_checks["document_active"] = False
                    if "mismatch" in w:
                        compliance_checks["cross_field_consistent"] = False

            # Check if critical mandatory fields are missing
            mandatory = self.MANDATORY_FIELDS.get(document_type, ["name"])
            missing_mandatory = [f for f in mandatory if not fields.get(f)]
            if missing_mandatory:
                compliance_checks["mandatory_fields_present"] = False
                fail_reasons.append(f"Missing mandatory required fields: {', '.join(missing_mandatory)}")

            if fail_reasons:
                return AgentResponse(
                    success=True,
                    data=RoutingResult(
                        status="FAIL",
                        reasons=fail_reasons,
                        risk_score=0.95,
                        review_flags=[w for w in warnings if w in self.CRITICAL_FAIL_WARNINGS],
                        compliance_checks=compliance_checks,
                    ),
                )

            # 3. Check for manual review criteria
            manual_reasons = []
            for w in warnings:
                if w in self.MANUAL_REVIEW_WARNINGS:
                    manual_reasons.append(self.MANUAL_REVIEW_WARNINGS[w])
                    review_flags.append(w)
                    if "scan_quality" in w:
                        compliance_checks["scan_quality_acceptable"] = False
                elif w.startswith("invalid_date_format_"):
                    field_name = w.replace("invalid_date_format_", "")
                    manual_reasons.append(f"Date format irregularity in field '{field_name}'")
                    review_flags.append(w)

            # Check overall classification confidence
            if confidence < self.min_pass_confidence:
                manual_reasons.append(f"Classification confidence ({confidence:.1%}) below automated pass threshold ({self.min_pass_confidence:.1%})")
                review_flags.append("low_classification_confidence")

            # Check individual critical field confidence scores
            low_conf_fields = [
                f for f in mandatory
                if field_confidence.get(f, 1.0) < self.critical_field_min_confidence
            ]
            if low_conf_fields:
                manual_reasons.append(f"Low extraction confidence on critical fields: {', '.join(low_conf_fields)}")
                review_flags.append("low_field_confidence")

            if manual_reasons:
                return AgentResponse(
                    success=True,
                    data=RoutingResult(
                        status="MANUAL_REVIEW",
                        reasons=manual_reasons,
                        risk_score=0.45,
                        review_flags=review_flags,
                        compliance_checks=compliance_checks,
                    ),
                )

            # 4. If all checks passed successfully -> PASS
            pass_reasons = [
                "Document format identified and validated with high confidence",
                "All mandatory identity fields successfully extracted and verified",
                "All cryptographic/format checksums passed",
                "Cross-field consistency verified with zero critical warnings",
            ]
            if document_type == "aadhaar":
                pass_reasons.append("Mandatory 8-digit Aadhaar PII masking enforced")

            return AgentResponse(
                success=True,
                data=RoutingResult(
                    status="PASS",
                    reasons=pass_reasons,
                    risk_score=0.05,
                    review_flags=[],
                    compliance_checks=compliance_checks,
                ),
            )

        except Exception as e:
            logger.error(f"Error in routing evaluation: {e}")
            return AgentResponse(
                success=False,
                error=f"Routing evaluation failed: {e}",
            )
