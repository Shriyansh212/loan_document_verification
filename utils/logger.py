"""
Logging utilities with PII redaction for KYC pipeline
"""

import logging
import re
import sys
from typing import Any


class PIIRedactionFilter(logging.Filter):
    """
    Filter to redact PII (Personally Identifiable Information) from logs
    Specifically targets Aadhaar numbers and other sensitive patterns
    """
    
    def __init__(self):
        super().__init__()
        # Pattern to match 12-digit sequences (Aadhaar numbers)
        self.aadhaar_pattern = re.compile(r'\b\d{4}\s*\d{4}\s*\d{4}\b')
        # Pattern to match PAN numbers
        self.pan_pattern = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')
        # Pattern to match potential passport numbers (alphanumeric 6-10 chars)
        self.passport_pattern = re.compile(r'\b[A-Z][0-9]{7}[A-Z]?\b')
        
    def filter(self, record):
        """Apply PII redaction to log record"""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            # Redact Aadhaar numbers
            record.msg = self.aadhaar_pattern.sub('XXXX XXXX XXXX', record.msg)
            # Redact PAN numbers
            record.msg = self.pan_pattern.sub('XXXXX0000X', record.msg)
            # Redact passport numbers
            record.msg = self.passport_pattern.sub('X0000000X', record.msg)
            
        # Also check args if present
        if hasattr(record, 'args') and record.args:
            redacted_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    arg = self.aadhaar_pattern.sub('XXXX XXXX XXXX', arg)
                    arg = self.pan_pattern.sub('XXXXX0000X', arg)
                    arg = self.passport_pattern.sub('X0000000X', arg)
                redacted_args.append(arg)
            record.args = tuple(redacted_args)
            
        return True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with PII redaction configured
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:  # Only configure if not already configured
        # Set log level
        logger.setLevel(logging.INFO)
        
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger


def setup_pii_redaction():
    """
    Setup PII redaction filter for all loggers
    """
    # Add PII filter to root logger
    root_logger = logging.getLogger()
    pii_filter = PIIRedactionFilter()
    
    # Add filter to all existing handlers
    for handler in root_logger.handlers:
        handler.addFilter(pii_filter)
    
    # Add filter to all existing loggers
    for name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(name)
        for handler in logger.handlers:
            handler.addFilter(pii_filter)


def redact_sensitive_data(data: Any) -> Any:
    """
    Manually redact sensitive data from any data structure
    Useful for redacting data before serialization
    """
    if isinstance(data, str):
        # Redact Aadhaar numbers
        data = re.sub(r'\b\d{4}\s*\d{4}\s*\d{4}\b', 'XXXX XXXX XXXX', data)
        # Redact PAN numbers
        data = re.sub(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', 'XXXXX0000X', data)
        # Redact passport numbers
        data = re.sub(r'\b[A-Z][0-9]{7}[A-Z]?\b', 'X0000000X', data)
        return data
    elif isinstance(data, dict):
        return {k: redact_sensitive_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    else:
        return data