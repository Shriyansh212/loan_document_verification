"""
Database package for KYC Document Verification Pipeline.
Provides SQLite-backed persistence for verification results and stage audit logs.
"""
from database.connection import get_db, init_db
from database.models import VerificationRecord, StageAuditLog
from database.crud import (
    save_verification_record,
    get_verification_record,
    list_verification_records,
    get_stage_audit_logs,
    get_verification_stats,
)

__all__ = [
    "get_db",
    "init_db",
    "VerificationRecord",
    "StageAuditLog",
    "save_verification_record",
    "get_verification_record",
    "list_verification_records",
    "get_stage_audit_logs",
    "get_verification_stats",
]
