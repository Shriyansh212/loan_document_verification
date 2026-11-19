"""
Ingestion Agent - File format detection and routing logic
"""

import tempfile
import os
from typing import Optional
from fastapi import UploadFile

from models.schemas import IngestionResult, AgentResponse
from agents.pdf_text_agent import PDFTextAgent
from agents.ocr_agent import OCRAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class IngestionAgent:
    """
    Ingestion Agent - Detects file format and decides processing path
    
    Logic:
    - If PDF: attempt pdfplumber text extraction
      - If extracted_text.strip() != "": route → PDF Text Agent
      - Else: route → OCR Agent (scanned/image-only PDF)
    - Else (image formats): route → OCR Agent
    """
    
    def __init__(self):
        self.pdf_text_agent = PDFTextAgent()
        self.ocr_agent = OCRAgent()
    
    async def process_file(self, file: UploadFile) -> AgentResponse:
        """
        Process uploaded file and route to appropriate agent
        
        Args:
            file: Uploaded file from FastAPI
            
        Returns:
            AgentResponse with IngestionResult data
        """
        try:
            logger.info(f"Starting ingestion for file: {file.filename}")
            
            # Create temporary file for processing
            with tempfile.NamedTemporaryFile(delete=False, suffix=self._get_file_extension(file.filename)) as temp_file:
                # Write uploaded file content to temporary file
                content = await file.read()
                temp_file.write(content)
                temp_file.flush()
                temp_file_path = temp_file.name
            
            try:
                # Determine file type and processing path
                file_type = self._determine_file_type(file.content_type, file.filename)
                logger.info(f"Detected file type: {file_type}")
                
                if file_type == "pdf":
                    # Try PDF text extraction first
                    logger.info("Attempting PDF text extraction...")
                    pdf_result = await self.pdf_text_agent.extract_text(temp_file_path)
                    
                    if pdf_result.success and pdf_result.data.strip():
                        # PDF has extractable text
                        logger.info("PDF contains extractable text, using PDF Text Agent")
                        return AgentResponse(
                            success=True,
                            data=IngestionResult(
                                raw_text=pdf_result.data,
                                processing_path="pdf_text",
                                file_type="pdf"
                            )
                        )
                    else:
                        # PDF is scanned or image-only, use OCR
                        logger.info("PDF appears to be scanned, routing to OCR Agent")
                        ocr_result = await self.ocr_agent.extract_text(temp_file_path)
                        
                        if not ocr_result.success:
                            return AgentResponse(
                                success=False,
                                error=f"OCR processing failed: {ocr_result.error}"
                            )
                        
                        return AgentResponse(
                            success=True,
                            data=IngestionResult(
                                raw_text=ocr_result.data,
                                processing_path="ocr",
                                file_type="pdf"
                            ),
                            warnings=ocr_result.warnings
                        )
                
                else:
                    # Image file, use OCR
                    logger.info(f"Image file detected ({file_type}), routing to OCR Agent")
                    ocr_result = await self.ocr_agent.extract_text(temp_file_path)
                    
                    if not ocr_result.success:
                        return AgentResponse(
                            success=False,
                            error=f"OCR processing failed: {ocr_result.error}"
                        )
                    
                    return AgentResponse(
                        success=True,
                        data=IngestionResult(
                            raw_text=ocr_result.data,
                            processing_path="ocr",
                            file_type=file_type
                        ),
                        warnings=ocr_result.warnings
                    )
            
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error in ingestion agent: {str(e)}")
            return AgentResponse(
                success=False,
                error=f"Ingestion failed: {str(e)}"
            )
    
    def _determine_file_type(self, content_type: str, filename: str) -> str:
        """
        Determine file type from content type and filename
        
        Args:
            content_type: MIME type from upload
            filename: Original filename
            
        Returns:
            File type string: "pdf" or "image"
        """
        if content_type == "application/pdf":
            return "pdf"
        elif content_type.startswith("image/"):
            return "image"
        else:
            # Fallback to filename extension
            if filename and filename.lower().endswith('.pdf'):
                return "pdf"
            else:
                return "image"
    
    def _get_file_extension(self, filename: str) -> str:
        """
        Get file extension from filename
        
        Args:
            filename: Original filename
            
        Returns:
            File extension with dot (e.g., ".pdf", ".png")
        """
        if not filename:
            return ""
        
        # Extract extension
        if '.' in filename:
            return '.' + filename.split('.')[-1].lower()
        else:
            return ""
    
    async def validate_file_content(self, file_path: str) -> bool:
        """
        Validate that file content is readable
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is readable, False otherwise
        """
        try:
            with open(file_path, 'rb') as f:
                # Read first few bytes to check if file is not empty/corrupted
                header = f.read(512)
                return len(header) > 0
        except Exception as e:
            logger.error(f"File validation failed: {e}")
            return False