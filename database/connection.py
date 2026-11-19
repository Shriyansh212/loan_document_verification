"""
Database connection and initialization module for SQLite storage.
Uses standard library sqlite3 for maximum portability and zero setup overhead.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "kyc_verification.db"))


def get_connection() -> sqlite3.Connection:
    """Create a new database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high-throughput reads/writes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for safe database transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database tables and indexes."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Table: verification_records
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verification_id TEXT UNIQUE NOT NULL,
            document_type TEXT,
            filename TEXT,
            file_type TEXT,
            file_size_bytes INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            routing_status TEXT NOT NULL,
            routing_reasons TEXT DEFAULT '[]',
            extracted_fields TEXT DEFAULT '{}',
            masked_fields TEXT DEFAULT '{}',
            field_level_scores TEXT DEFAULT '{}',
            warnings TEXT DEFAULT '[]',
            masked BOOLEAN DEFAULT 0,
            processing_time_ms REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Table: stage_audit_logs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stage_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verification_id TEXT NOT NULL,
            stage_name TEXT NOT NULL,
            status TEXT NOT NULL,
            execution_time_ms REAL DEFAULT 0.0,
            input_summary TEXT,
            output_summary TEXT,
            details TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (verification_id) REFERENCES verification_records (verification_id) ON DELETE CASCADE
        );
        """)

        # Indexes for fast querying & filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_status ON verification_records(routing_status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_doc_type ON verification_records(document_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_created ON verification_records(created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_vid ON stage_audit_logs(verification_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_stage ON stage_audit_logs(stage_name);")
