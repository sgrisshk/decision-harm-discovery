import logging

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analysis_runs.routes import router as analysis_runs_router
from app.api.schemas import HealthResponse
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.datasets.routes import router as datasets_router
from app.db.session import get_db
from app.findings.routes import router as findings_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("policy_api")

app = FastAPI(
    title="Policy Discovery API",
    version="0.1.0",
    debug=False,
    docs_url="/docs",
    redoc_url=None,
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "x-request-id"],
)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse, tags=["operations"])
def ready(session: Session = Depends(get_db)) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("readiness_failed", extra={"fields": {"component": "database"}})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready"
        ) from exc
    return HealthResponse(status="ready")


app.include_router(datasets_router, prefix="/api/v1")
app.include_router(analysis_runs_router, prefix="/api/v1")
app.include_router(findings_router, prefix="/api/v1")
