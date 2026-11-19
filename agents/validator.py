"""
Validator Agent - Validates extracted fields with document-specific rules.
Implements PAN regex, Aadhaar Luhn algorithm, DL validity dates,
and ICAO Doc 9303 Passport MRZ check digits.
"""

import re
from datetime import datetime, date
from typing import Dict, Any, List
from models.schemas import ValidatorResult, AgentResponse
from utils.logger import get_logger

logger = get_logger(__name__)

# Safe MRZ imports with pure-Python fallback
try:
    from mrz.checker.td3 import TD3CodeChecker
    HAS_MRZ_LIB = True
except ImportError:
    HAS_MRZ_LIB = False


def compute_mrz_check_digit(s: str) -> int:
    """Compute ICAO 9303 check digit with 7-3-1 weight progression."""
    weights = [7, 3, 1]
    total = 0
    for i, c in enumerate(s):
        if c == "<":
            val = 0
        elif c.isdigit():
            val = int(c)
        elif c.isalpha():
            val = ord(c.upper()) - 55
        else:
            val = 0
        total += val * weights[i % 3]
    return total % 10


class ValidatorAgent:
    """
    Validator Agent - Validates extracted fields using document-specific rules.
    """

    def __init__(self):
        self.name = "Validator Agent"
        self.pan_regex = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
        self.date_regex = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    async def validate_fields(self, fields: Dict[str, Any], document_type: str) -> AgentResponse:
        try:
            logger.info(f"Starting field validation for document type: {document_type}")
            warnings: List[str] = []

            # Document-specific validations
            if document_type == "aadhaar":
                warnings.extend(self._validate_aadhaar(fields))
            elif document_type == "pan":
                warnings.extend(self._validate_pan(fields))
            elif document_type == "voter_id":
                warnings.extend(self._validate_voter_id(fields))
            elif document_type == "driving_licence":
                warnings.extend(self._validate_driving_licence(fields))
            elif document_type == "passport":
                warnings.extend(self._validate_passport(fields))

            # Common validations
            warnings.extend(self._validate_common_fields(fields))

            logger.info(f"Validation completed. {len(warnings)} warnings generated")

            return AgentResponse(
                success=True,
                data=ValidatorResult(
                    warnings=warnings,
                    is_valid=(len(warnings) == 0),
                ),
            )

        except Exception as e:
            logger.error(f"Error in field validation: {e}")
            return AgentResponse(
                success=False,
                error=f"Validation failed: {str(e)}",
            )

    def _validate_aadhaar(self, fields: Dict[str, Any]) -> List[str]:
        warnings = []
        aadhaar_number = fields.get("aadhaar_number")
        if aadhaar_number:
            clean_aadhaar = str(aadhaar_number).replace(" ", "")
            if len(clean_aadhaar) != 12:
                warnings.append("aadhaar_invalid_length")
            elif not clean_aadhaar.isdigit():
                warnings.append("aadhaar_invalid_format")
            elif not (self._validate_verhoeff(clean_aadhaar) or self._validate_luhn(clean_aadhaar)):
                warnings.append("aadhaar_checksum_failed")

        gender = fields.get("gender")
        if gender and gender not in ["M", "F", "O"]:
            warnings.append("aadhaar_invalid_gender")

        return warnings

    def _validate_pan(self, fields: Dict[str, Any]) -> List[str]:
        warnings = []
        pan_number = fields.get("pan_number")
        if pan_number:
            if not self.pan_regex.match(str(pan_number).strip().upper()):
                warnings.append("pan_format_invalid")
        return warnings

    def _validate_voter_id(self, fields: Dict[str, Any]) -> List[str]:
        return []

    def _validate_driving_licence(self, fields: Dict[str, Any]) -> List[str]:
        warnings = []
        valid_until = fields.get("valid_until")
        if valid_until:
            try:
                expiry_date = datetime.strptime(valid_until, "%Y-%m-%d").date()
                if expiry_date <= date.today():
                    warnings.append("dl_expired")
            except ValueError:
                warnings.append("dl_invalid_expiry_format")

        valid_from = fields.get("valid_from")
        if valid_from and valid_until:
            try:
                from_date = datetime.strptime(valid_from, "%Y-%m-%d").date()
                until_date = datetime.strptime(valid_until, "%Y-%m-%d").date()
                if from_date >= until_date:
                    warnings.append("dl_invalid_date_range")
            except ValueError:
                pass

        return warnings

    def _validate_passport(self, fields: Dict[str, Any]) -> List[str]:
        warnings = []
        nationality = fields.get("nationality")
        if nationality and len(str(nationality)) != 3:
            warnings.append("passport_invalid_nationality_format")

        expiry_date = fields.get("expiry_date")
        if expiry_date:
            try:
                exp = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                if exp <= date.today():
                    warnings.append("passport_expired")
            except ValueError:
                warnings.append("invalid_date_format_expiry_date")

        mrz_line = fields.get("mrz_line")
        if mrz_line:
            warnings.extend(self._validate_mrz(str(mrz_line).strip(), fields))

        return warnings

    def _validate_mrz(self, mrz_line: str, fields: Dict[str, Any]) -> List[str]:
        warnings = []
        try:
            if HAS_MRZ_LIB:
                # TD3 check
                lines = [mrz_line[i:i+30] for i in range(0, min(len(mrz_line), 90), 30)]
                if len(lines) == 3 or len(mrz_line) >= 44:
                    try:
                        checker = TD3CodeChecker('\n'.join(lines))
                        if not checker.check():
                            warnings.append("mrz_checksum_failed")
                        mrz_fields = checker.fields()
                        if fields.get("passport_number") and mrz_fields.get("document_number"):
                            if fields["passport_number"].replace(" ", "") != mrz_fields["document_number"]:
                                warnings.append("mrz_passport_number_mismatch")
                        return warnings
                    except Exception:
                        pass

            # Pure-Python ICAO check
            if len(mrz_line) >= 9:
                pass_no = fields.get("passport_number", "")
                if pass_no and len(pass_no) == 8:
                    # Verify passport check digit if available in MRZ substring
                    num_sub = mrz_line[:8]
                    if num_sub.isalnum():
                        expected = compute_mrz_check_digit(num_sub)
                        if len(mrz_line) > 8 and mrz_line[8].isdigit():
                            actual = int(mrz_line[8])
                            if expected != actual:
                                warnings.append("mrz_checksum_failed")
        except Exception as e:
            logger.warning(f"MRZ validation fallback warning: {e}")

        return warnings

    def _validate_common_fields(self, fields: Dict[str, Any]) -> List[str]:
        warnings = []
        date_fields = ["dob", "valid_from", "valid_until", "expiry_date"]
        for field_name in date_fields:
            if field_name in fields and fields[field_name]:
                if not self._validate_date_format(str(fields[field_name])):
                    warnings.append(f"invalid_date_format_{field_name}")

        name = fields.get("name")
        if name and (not str(name).strip() or len(str(name).strip()) < 2):
            warnings.append("name_too_short")

        return warnings

    def _validate_date_format(self, date_str: str) -> bool:
        try:
            if not self.date_regex.match(date_str):
                return False
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _validate_verhoeff(self, num_str: str) -> bool:
        """Official UIDAI Aadhaar Verhoeff algorithm check."""
        d = [
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
            [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
            [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
            [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
            [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
            [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
            [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
            [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
            [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
            [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
        ]
        p = [
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
            [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
            [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
            [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
            [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
            [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
            [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
            [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
        ]
        try:
            c = 0
            rev = str(num_str)[::-1]
            for i in range(len(rev)):
                c = d[c][p[i % 8][int(rev[i])]]
            return c == 0
        except Exception:
            return False

    def _validate_luhn(self, number_str: str) -> bool:
        """Validate 12-digit number using standard Luhn algorithm."""
        try:
            def luhn_checksum(card_num):
                digits = [int(d) for d in str(card_num)]
                odd_digits = digits[-1::-2]
                even_digits = digits[-2::-2]
                checksum = sum(odd_digits)
                for d in even_digits:
                    checksum += sum(int(n) for n in str(d * 2))
                return checksum % 10

            return luhn_checksum(number_str) == 0
        except Exception:
            return False
