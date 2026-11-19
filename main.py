"""
KYC Document Verification Pipeline - LLM Extraction
FastAPI application entry point
"""

import os
from contextlib import asynccontextmanager
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from agents.orchestrator import router as orchestrator_router
from database.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure SQLite database tables & indexes are initialized
    init_db()
    yield


app = FastAPI(
    title="Document Verification Pipeline - LLM Extraction",
    description="Multi-stage production-style pipeline (OCR -> LLM extraction -> validation -> routing) with SQL-backed result storage and audit logs.",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static assets
if os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="frontend/templates")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(orchestrator_router, prefix="/api/v1/kyc", tags=["KYC Pipeline"])


@app.get("/", response_class=HTMLResponse)
async def frontend(request: Request):
    """Serve the modern interactive frontend"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/demo", response_class=HTMLResponse)
async def demo(request: Request):
    """Serve the live demo and document capabilities showcase"""
    return templates.TemplateResponse("demo.html", {"request": request})


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "document-verification-pipeline",
        "model": "Groq Llama 3.3 (llama-3.3-70b-versatile)",
        "database": "SQLite (WAL mode)",
        "routing": ["PASS", "FAIL", "MANUAL_REVIEW"],
    }


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level=log_level,
    )
