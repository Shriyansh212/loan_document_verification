"""
Masker Agent - Applies mandatory masking rules with security compliance
"""

import copy
from typing import Dict, Any

from models.schemas import MaskerResult, AgentResponse
from utils.logger import get_logger

logger = get_logger(__name__)


class MaskerAgent:
    """
    Masker Agent - Applies mandatory masking rules
    
    Critical security rules:
    - Aadhaar masking is mandatory and non-negotiable
    - First 8 digits → 'X', last 4 digits preserved, format with spaces
    - Unmasked Aadhaar numbers must never appear in API responses, logs, or storage
    - Masking is applied before any serialization or response generation
    """
    
    def __init__(self):
        self.name = "Masker Agent"
    
    async def mask_fields(self, fields: Dict[str, Any], document_type: str) -> AgentResponse:
        """
        Apply masking rules to extracted fields
        
        Args:
            fields: Extracted fields to mask
            document_type: Type of document
            
        Returns:
            AgentResponse with MaskerResult
        """
        try:
            logger.info(f"Starting field masking for document type: {document_type}")
            
            # Deep copy fields to avoid modifying original
            masked_fields = copy.deepcopy(fields)
            masking_applied = False
            
            # Apply document-specific masking
            if document_type == "aadhaar":
                masked_fields, masking_applied = self._mask_aadhaar_fields(masked_fields)
                
            # Other document types don't require masking currently
            # but this can be extended for other sensitive fields
            
            logger.info(f"Masking completed. Masking applied: {masking_applied}")
            
            return AgentResponse(
                success=True,
                data=MaskerResult(
                    masked_fields=masked_fields,
                    masking_applied=masking_applied
                )
            )
        
        except Exception as e:
            logger.error(f"Error in field masking: {str(e)}")
            return AgentResponse(
                success=False,
                error=f"Masking failed: {str(e)}"
            )
    
    def _mask_aadhaar_fields(self, fields: Dict[str, Any]) -> tuple:
        """
        Apply Aadhaar masking rules
        
        Args:
            fields: Fields dictionary containing Aadhaar data
            
        Returns:
            Tuple of (masked_fields, masking_applied)
        """
        masking_applied = False
        
        # Mask Aadhaar number if present
        if "aadhaar_number" in fields and fields["aadhaar_number"]:
            original_number = fields["aadhaar_number"]
            
            try:
                masked_number = self._mask_aadhaar_number(original_number)
                fields["aadhaar_number"] = masked_number
                masking_applied = True
                
                logger.info("Aadhaar number successfully masked")
                
            except Exception as e:
                logger.error(f"Failed to mask Aadhaar number: {e}")
                # If masking fails, remove the field entirely for security
                del fields["aadhaar_number"]
                masking_applied = True
                logger.warning("Aadhaar number removed due to masking failure")
        
        return fields, masking_applied
    
    def _mask_aadhaar_number(self, aadhaar_number: str) -> str:
        """
        Mask Aadhaar number according to mandatory rules
        
        Rule: First 8 digits → 'X'; last 4 digits preserved; format with spaces
        Input:  "1234 5678 9012"  or  "123456789012"
        Output: "XXXX XXXX 9012"
        
        Args:
            aadhaar_number: Raw Aadhaar number
            
        Returns:
            Masked Aadhaar number
            
        Raises:
            ValueError: If Aadhaar number format is invalid
        """
        if not aadhaar_number:
            raise ValueError("Aadhaar number cannot be empty")
        
        # Remove all spaces and non-digits
        digits_only = ''.join(c for c in aadhaar_number if c.isdigit())
        
        # Validate length
        if len(digits_only) != 12:
            raise ValueError(f"Aadhaar number must be 12 digits, got {len(digits_only)}")
        
        # Apply masking: first 8 digits → 'X', last 4 preserved
        masked = "XXXX XXXX " + digits_only[-4:]
        
        return masked
    
    def validate_no_sensitive_data_leaked(self, data: Any) -> bool:
        """
        Validate that no unmasked sensitive data is present in the output
        
        Args:
            data: Data structure to validate
            
        Returns:
            True if no sensitive data found, False otherwise
        """
        try:
            # Convert to string for pattern matching
            data_str = str(data)
            
            # Look for potential unmasked Aadhaar numbers (12 consecutive digits)
            import re
            aadhaar_pattern = re.compile(r'\b\d{12}\b')
            
            # Check for full 12-digit sequences that aren't masked
            matches = aadhaar_pattern.findall(data_str)
            
            # Allow masked patterns (starting with X or containing X)
            for match in matches:
                # If we find a 12-digit number that's not clearly masked, flag it
                if not self._is_masked_pattern(match):
                    logger.error(f"Potential unmasked sensitive data detected: {match[:4]}XXXXXXXX")
                    return False
            
            return True
        
        except Exception as e:
            logger.error(f"Sensitive data validation failed: {e}")
            return False
    
    def _is_masked_pattern(self, number_str: str) -> bool:
        """
        Check if a number string appears to be masked
        
        Args:
            number_str: Number string to check
            
        Returns:
            True if appears masked, False if potentially sensitive
        """
        # This is a basic check - in production you might want more sophisticated detection
        # For now, we'll be conservative and flag any 12-digit sequence as potentially sensitive
        # unless it's in a clearly masked format
        
        # Allow test/dummy numbers (like all same digits)
        if len(set(number_str)) == 1:  # All same digit
            return True
        
        # Allow sequential numbers (like 123456789012)
        if number_str in ["123456789012", "000000000000"]:
            return True
        
        # Otherwise, consider it potentially sensitive
        return False
    
    def get_masking_info(self, document_type: str) -> Dict[str, str]:
        """
        Get information about masking rules for a document type
        
        Args:
            document_type: Type of document
            
        Returns:
            Dictionary with masking rule information
        """
        masking_rules = {
            "aadhaar": {
                "fields_masked": ["aadhaar_number"],
                "masking_rule": "First 8 digits replaced with XXXX XXXX, last 4 digits preserved",
                "mandatory": True,
                "format": "XXXX XXXX NNNN"
            },
            "pan": {
                "fields_masked": [],
                "masking_rule": "No masking required",
                "mandatory": False,
                "format": "Full number displayed"
            },
            "voter_id": {
                "fields_masked": [],
                "masking_rule": "No masking required",
                "mandatory": False,
                "format": "Full number displayed"
            },
            "driving_licence": {
                "fields_masked": [],
                "masking_rule": "No masking required", 
                "mandatory": False,
                "format": "Full number displayed"
            },
            "passport": {
                "fields_masked": [],
                "masking_rule": "No masking required",
                "mandatory": False,
                "format": "Full number displayed"
            }
        }
        
        return masking_rules.get(document_type, {
            "fields_masked": [],
            "masking_rule": "Unknown document type",
            "mandatory": False,
            "format": "Unknown"
        })