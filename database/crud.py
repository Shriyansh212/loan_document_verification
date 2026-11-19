"""
CRUD operations for verification records and stage audit logs.
"""

import json
from typing import Any, Dict, List, Optional
from database.connection import get_db


def save_verification_record(record: Dict[str, Any], audit_logs: List[Dict[str, Any]]) -> str:
    """
    Save a completed verification record and its stage audit logs in a single transaction.
    Returns the verification_id.
    """
    verification_id = record["verification_id"]

    with get_db() as conn:
        cursor = conn.cursor()

        # Insert verification record
        cursor.execute(
            """
            INSERT INTO verification_records (
                verification_id, document_type, filename, file_type, file_size_bytes,
                confidence, routing_status, routing_reasons, extracted_fields,
                masked_fields, field_level_scores, warnings, masked, processing_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verification_id,
                record.get("document_type"),
                record.get("filename"),
                record.get("file_type"),
                record.get("file_size_bytes", 0),
                record.get("confidence", 0.0),
                record.get("routing_status", "MANUAL_REVIEW"),
                json.dumps(record.get("routing_reasons", [])),
                json.dumps(record.get("extracted_fields", {})),
                json.dumps(record.get("masked_fields", {})),
                json.dumps(record.get("field_level_scores", {})),
                json.dumps(record.get("warnings", [])),
                1 if record.get("masked", False) else 0,
                record.get("processing_time_ms", 0.0),
            ),
        )

        # Insert each stage audit log
        for audit in audit_logs:
            cursor.execute(
                """
                INSERT INTO stage_audit_logs (
                    verification_id, stage_name, status, execution_time_ms,
                    input_summary, output_summary, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verification_id,
                    audit.get("stage_name", "Unknown"),
                    audit.get("status", "SUCCESS"),
                    audit.get("execution_time_ms", 0.0),
                    audit.get("input_summary", ""),
                    audit.get("output_summary", ""),
                    json.dumps(audit.get("details", {})),
                ),
            )

    return verification_id


def get_verification_record(verification_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single verification record along with its audit logs."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM verification_records WHERE verification_id = ?", (verification_id,))
        row = cursor.fetchone()
        if not row:
            return None

        record = dict(row)
        record["routing_reasons"] = json.loads(record.get("routing_reasons") or "[]")
        record["extracted_fields"] = json.loads(record.get("extracted_fields") or "{}")
        record["masked_fields"] = json.loads(record.get("masked_fields") or "{}")
        record["field_level_scores"] = json.loads(record.get("field_level_scores") or "{}")
        record["warnings"] = json.loads(record.get("warnings") or "[]")
        record["masked"] = bool(record.get("masked", 0))

        # Get audit logs
        record["audit_logs"] = get_stage_audit_logs(verification_id)
        return record


def list_verification_records(
    status_filter: Optional[str] = None,
    doc_type_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List verification records with optional filters."""
    query = "SELECT * FROM verification_records WHERE 1=1"
    params: List[Any] = []

    if status_filter and status_filter.upper() != "ALL":
        query += " AND routing_status = ?"
        params.append(status_filter.upper())

    if doc_type_filter and doc_type_filter.lower() != "all":
        query += " AND document_type = ?"
        params.append(doc_type_filter.lower())

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for r in rows:
            rec = dict(r)
            rec["routing_reasons"] = json.loads(rec.get("routing_reasons") or "[]")
            rec["masked_fields"] = json.loads(rec.get("masked_fields") or "{}")
            rec["warnings"] = json.loads(rec.get("warnings") or "[]")
            rec["masked"] = bool(rec.get("masked", 0))
            results.append(rec)
        return results


def get_stage_audit_logs(verification_id: str) -> List[Dict[str, Any]]:
    """Retrieve all stage audit logs for a verification ID in chronological order."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM stage_audit_logs WHERE verification_id = ? ORDER BY id ASC",
            (verification_id,),
        )
        rows = cursor.fetchall()
        logs = []
        for r in rows:
            item = dict(r)
            item["details"] = json.loads(item.get("details") or "{}")
            logs.append(item)
        return logs


def get_verification_stats() -> Dict[str, Any]:
    """Calculate aggregate statistics across all verification runs."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM verification_records")
        total = cursor.fetchone()[0]

        if total == 0:
            return {
                "total_processed": 0,
                "pass_count": 0,
                "fail_count": 0,
                "manual_review_count": 0,
                "pass_rate_percent": 0.0,
                "avg_latency_ms": 0.0,
                "document_distribution": {},
            }

        cursor.execute("SELECT COUNT(*) FROM verification_records WHERE routing_status = 'PASS'")
        pass_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM verification_records WHERE routing_status = 'FAIL'")
        fail_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM verification_records WHERE routing_status = 'MANUAL_REVIEW'")
        manual_review_count = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(processing_time_ms) FROM verification_records")
        avg_latency = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT document_type, COUNT(*) FROM verification_records GROUP BY document_type")
        doc_dist = {row[0] or "unknown": row[1] for row in cursor.fetchall()}

        return {
            "total_processed": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "manual_review_count": manual_review_count,
            "pass_rate_percent": round((pass_count / total) * 100, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "document_distribution": doc_dist,
        }
