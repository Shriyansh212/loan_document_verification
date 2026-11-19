"""
PDF Text Agent - Extracts raw text from digital PDFs using pdfplumber with pypdf fallback.
"""

from typing import Optional
from pathlib import Path
from models.schemas import AgentResponse
from utils.logger import get_logger

logger = get_logger(__name__)

# Safe imports for pdf extraction
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


class PDFTextAgent:
    """
    PDF Text Agent - Extracts raw text from digital PDFs
    """

    def __init__(self):
        self.name = "PDF Text Agent"

    async def extract_text(self, file_path: str) -> AgentResponse:
        try:
            logger.info(f"Starting PDF text extraction for: {file_path}")

            if not Path(file_path).exists():
                return AgentResponse(
                    success=False,
                    error=f"PDF file not found: {file_path}",
                )

            extracted_text = ""

            # Attempt 1: pdfplumber
            if HAS_PDFPLUMBER:
                try:
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            text = page.extract_text()
                            if text:
                                extracted_text += text + "\n"
                    if extracted_text.strip():
                        return AgentResponse(success=True, data=extracted_text.strip())
                except Exception as e:
                    logger.warning(f"pdfplumber failed ({e}), trying pypdf fallback...")

            # Attempt 2: pypdf fallback
            if HAS_PYPDF:
                try:
                    reader = pypdf.PdfReader(file_path)
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            extracted_text += text + "\n"
                    if extracted_text.strip():
                        return AgentResponse(success=True, data=extracted_text.strip())
                except Exception as e:
                    logger.warning(f"pypdf extraction failed: {e}")

            if not extracted_text.strip():
                return AgentResponse(
                    success=False,
                    error="No selectable digital text found in PDF (may be a scanned document)",
                )

            return AgentResponse(success=True, data=extracted_text.strip())

        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            return AgentResponse(
                success=False,
                error=f"PDF text extraction failed: {str(e)}",
            )
