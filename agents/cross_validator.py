"""
Cross-Document Validator Agent - Multi-document identity cross-matching.
Performs cross-field reconciliation between Primary ID (e.g., PAN) and Secondary ID (e.g., Aadhaar).
"""

import re
from typing import Any, Dict, List, Tuple
from models.schemas import (
    CrossDocumentConsistency,
    MultiDocumentVerificationResult,
    ProcessingResult,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def normalize_name(name: str) -> str:
    """Normalize names by stripping common titles, punctuation, and extra whitespace."""
    if not name:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    words = [w for w in cleaned.split() if w not in {"mr", "mrs", "shri", "smt", "ms", "dr", "kumar", "kumari"}]
    return " ".join(words).upper()


def compute_name_similarity(name1: str, name2: str) -> float:
    """Compute token-level and character similarity between two names."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return 0.0

    if n1 == n2:
        return 1.0

    tokens1 = set(n1.split())
    tokens2 = set(n2.split())

    # Check token overlap
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    jaccard = len(intersection) / len(union) if union else 0.0

    # Check if one is initial of the other (e.g. S GUPTA vs SHRIYANSH GUPTA)
    initials_match = False
    if len(tokens1) > 0 and len(tokens2) > 0:
        first1 = list(tokens1)[0]
        first2 = list(tokens2)[0]
        if (len(first1) == 1 or len(first2) == 1) and first1[0] == first2[0]:
            initials_match = True

    if jaccard >= 0.5 or initials_match:
        return max(0.80, jaccard)

    # Substring match
    if n1 in n2 or n2 in n1:
        return 0.85

    return jaccard


class CrossValidatorAgent:
    """
    Evaluates consistency across multiple submitted KYC/Loan documents.
    """

    def evaluate_cross_consistency(self, docs: List[ProcessingResult]) -> Tuple[CrossDocumentConsistency, str, List[str], float]:
        consistency = CrossDocumentConsistency()
        reasons: List[str] = []
        overall_status = "PASS"
        match_score = 1.0

        if len(docs) < 2:
            reasons.append("Single document verified. Submit 2+ documents (PAN + Aadhaar) for cross-identity matching.")
            return consistency, docs[0].routing_status if docs else "MANUAL_REVIEW", reasons, 1.0

        doc1, doc2 = docs[0], docs[1]
        name1 = doc1.fields.get("name", "")
        name2 = doc2.fields.get("name", "")
        dob1 = doc1.fields.get("dob", "")
        dob2 = doc2.fields.get("dob", "")
        fn1 = doc1.fields.get("fathers_name", "")
        fn2 = doc2.fields.get("fathers_name", "")
        g1 = doc1.fields.get("gender", "")
        g2 = doc2.fields.get("gender", "")

        consistency.name_doc1 = name1
        consistency.name_doc2 = name2
        consistency.dob_doc1 = dob1
        consistency.dob_doc2 = dob2
        consistency.fathers_name_doc1 = fn1
        consistency.fathers_name_doc2 = fn2
        consistency.gender_doc1 = g1
        consistency.gender_doc2 = g2

        # 1. Name cross-check
        if name1 and name2:
            sim = compute_name_similarity(name1, name2)
            consistency.name_similarity = round(sim, 2)

            if sim >= 0.85:
                reasons.append(f"Name match verified ({sim:.0%}): '{name1}' ⟷ '{name2}'")
            elif sim >= 0.70:
                consistency.name_match = False
                consistency.cross_warnings.append("name_partial_match")
                consistency.mismatch_details.append(f"Name variation detected ({sim:.0%}): '{name1}' vs '{name2}'")
                reasons.append(f"Name spelling variation ({sim:.0%}): requires manual verification")
                if overall_status == "PASS":
                    overall_status = "MANUAL_REVIEW"
                match_score = min(match_score, 0.75)
            else:
                consistency.name_match = False
                consistency.cross_warnings.append("name_mismatch")
                consistency.mismatch_details.append(f"Severe name mismatch: '{name1}' vs '{name2}'")
                reasons.append(f"Identity Mismatch: Name on Document 1 ('{name1}') does not match Document 2 ('{name2}')")
                overall_status = "FAIL"
                match_score = min(match_score, 0.20)
        else:
            reasons.append("Name missing on one of the documents for cross-comparison")
            if overall_status == "PASS":
                overall_status = "MANUAL_REVIEW"

        # 2. DOB cross-check
        if dob1 and dob2:
            if str(dob1).strip() == str(dob2).strip():
                reasons.append(f"Date of birth verified: {dob1} matches across both documents")
            else:
                consistency.dob_match = False
                consistency.cross_warnings.append("dob_mismatch")
                consistency.mismatch_details.append(f"DOB mismatch: '{dob1}' vs '{dob2}'")
                reasons.append(f"Critical Conflict: DOB '{dob1}' does not match '{dob2}'")
                overall_status = "FAIL"
                match_score = min(match_score, 0.10)

        # 3. Father's Name cross-check
        if fn1 and fn2:
            fn_sim = compute_name_similarity(fn1, fn2)
            if fn_sim >= 0.80:
                reasons.append(f"Father's name verified ({fn_sim:.0%}): '{fn1}' ⟷ '{fn2}'")
            elif fn_sim >= 0.60:
                consistency.fathers_name_match = False
                consistency.cross_warnings.append("fathers_name_partial_match")
                consistency.mismatch_details.append(f"Father's name variation ({fn_sim:.0%}): '{fn1}' vs '{fn2}'")
                reasons.append(f"Father's name variation ({fn_sim:.0%}): requires manual verification")
                if overall_status == "PASS":
                    overall_status = "MANUAL_REVIEW"
                match_score = min(match_score, 0.70)
            else:
                consistency.fathers_name_match = False
                consistency.cross_warnings.append("fathers_name_mismatch")
                consistency.mismatch_details.append(f"Father's name mismatch: '{fn1}' vs '{fn2}'")
                reasons.append(f"Critical Conflict: Father's Name on Document 1 ('{fn1}') does not match Document 2 ('{fn2}')")
                overall_status = "FAIL"
                match_score = min(match_score, 0.15)

        # 4. Gender cross-check
        if g1 and g2:
            g1_clean = str(g1).strip().upper()[:1]
            g2_clean = str(g2).strip().upper()[:1]
            if g1_clean in {"M", "F"} and g2_clean in {"M", "F"}:
                if g1_clean == g2_clean:
                    reasons.append(f"Gender verified: '{g1}' matches across documents")
                else:
                    consistency.gender_match = False
                    consistency.cross_warnings.append("gender_mismatch")
                    consistency.mismatch_details.append(f"Gender conflict: '{g1}' vs '{g2}'")
                    reasons.append(f"Identity Conflict: Gender on Document 1 ('{g1}') does not match Document 2 ('{g2}')")
                    overall_status = "FAIL"
                    match_score = min(match_score, 0.10)

        # 5. Individual Document Failure Check
        for i, d in enumerate(docs):
            if d.routing_status == "FAIL":
                overall_status = "FAIL"
                reasons.append(f"Document {i+1} ({d.document_type or 'Unknown'}) failed individual verification checks")
            elif d.routing_status == "MANUAL_REVIEW" and overall_status == "PASS":
                overall_status = "MANUAL_REVIEW"
                reasons.append(f"Document {i+1} flagged for manual review: {', '.join(d.routing_reasons)}")

        if overall_status == "PASS":
            reasons.insert(0, "Multi-document loan KYC verification SUCCESS: Identity records reconciled across all documents.")

        return consistency, overall_status, reasons, match_score
