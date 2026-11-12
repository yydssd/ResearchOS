"""FastAPI application with the minimal v1 API (plan §28).

P0 acceptance: `uvicorn research_os.main:app` starts and `/health` responds.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from research_os.config import settings
from research_os.storage.database import init_db, session_scope
from research_os.storage.repositories import (
    SqlClaimRepository,
    SqlRunRepository,
)
from research_os.orchestration.supervisor import Supervisor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


class HealthResponse(BaseModel):
    status: str
    app: str
    database: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check: confirms the app and its configured database URL."""
    return HealthResponse(status="ok", app=settings.app_name, database=settings.database_url)


class SourceSpecIn(BaseModel):
    path: str
    title: str = ""
    source_type: str = "auto"


class ResearchRequest(BaseModel):
    question: str = Field(min_length=3)
    domain: str | None = None
    sources: list[SourceSpecIn] = []


class RunCreated(BaseModel):
    run_id: str
    status: str


@app.post("/research", response_model=RunCreated)
def create_research(req: ResearchRequest) -> RunCreated:
    """Create a research run; when local sources are provided, executes the
    Week-1 vertical slice synchronously (question -> evidence -> claims -> memo)."""
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=req.question, domain=req.domain)
        if req.sources:
            supervisor.run_vertical_slice(
                run_id=run.id,
                sources=[(s.path, s.title or None, s.source_type) for s in req.sources],
            )
        return RunCreated(run_id=run.id, status=run.status.value)


@app.get("/research/{run_id}")
def get_run(run_id: str):
    """Return the lightweight run state (status, phase, warnings)."""
    with session_scope() as session:
        run = SqlRunRepository(session).get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run_id": run.id, "status": run.status.value, "phase": run.current_phase, "warnings": run.warnings}


@app.get("/research/{run_id}/report")
def get_report(run_id: str):
    """Return the Markdown research memo for a run."""
    from research_os.reporting.memo import build_memo_from_run

    with session_scope() as session:
        memo = build_memo_from_run(session, run_id)
        if memo is None:
            raise HTTPException(status_code=404, detail="run not found")
        return memo


@app.get("/research/{run_id}/claims")
def get_claims(run_id: str):
    """Return the claims scoped to this run."""
    with session_scope() as session:
        claims = SqlClaimRepository(session).list_by_run(run_id)
        if not claims:
            raise HTTPException(status_code=404, detail="run not found or has no claims")
        return [c.model_dump() for c in claims]
