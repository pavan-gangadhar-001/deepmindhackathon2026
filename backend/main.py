"""Prody engine backend — FastAPI + SSE on :8000.

The HTTP surface the Antigravity IDE extension and the dashboard consume to
start an engagement, watch the AI engineering team work live, approve critical
actions, and read production readiness.

Interface Contract (TASKS.md — do not break without logging):
    POST /api/session/start   { source, repo_url?, project_path? } -> { session_id }
    GET  /api/session/{id}/events   -> SSE: { type, agent, message, data? }
    POST /api/session/{id}/approve  { step_id } -> approval gate
    GET  /api/session/{id}/status   -> { phase, readiness_score?, deploy_url? }

`run_pipeline` is blocking, so each session runs on a background daemon thread;
the endpoints just read/write the shared `Session` it mutates.
"""
import engine.env  # noqa: F401 — load repo-root .env before other engine imports
import asyncio
import json
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from engine.intake import extract_zip_upload
from engine.orchestrator import run_pipeline
from engine.session import REGISTRY, Session, TERMINAL_STATUSES

app = FastAPI(title="Prody Engine")

# Dashboard (Next.js) + landing run on other origins in dev — allow them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SSE tuning.
STREAM_POLL_INTERVAL_S = 0.3
MAX_STREAM_POLLS = 4000  # ~20 min ceiling so a stream can't hang forever
UPLOAD_ROOT = Path(__file__).resolve().parent.parent / ".prody_uploads"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


class SessionStartRequest(BaseModel):
    source: str = "dashboard"                 # "ide" | "dashboard"
    repo_url: Optional[str] = None
    project_path: Optional[str] = None
    project_id: Optional[str] = None          # optional GCP project override
    region: Optional[str] = None
    service_name: Optional[str] = None


class ApproveRequest(BaseModel):
    step_id: Optional[str] = None
    approved: bool = True


def _get_session_or_404(session_id: str) -> Session:
    session = REGISTRY.get(session_id)
    if session is None:
        raise HTTPException(404, "session_id not found")
    return session


@app.get("/api/gemma/status")
def gemma_status():
    """Whether local Gemma (Ollama) is enabled and reachable."""
    from engine import gemma_local

    return gemma_local.status_dict()


@app.post("/api/upload/project")
async def upload_project(file: UploadFile = File(...)):
    """Accept a project .zip from the dashboard, extract it, return project_path."""
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".zip"):
        raise HTTPException(400, "upload a .zip file")

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex[:12]
    zip_path = UPLOAD_ROOT / f"{upload_id}.zip"

    size = 0
    try:
        with zip_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "zip exceeds 100 MB limit")
                out.write(chunk)
        project_path = extract_zip_upload(str(zip_path))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        zip_path.unlink(missing_ok=True)

    return {
        "project_path": project_path,
        "filename": filename,
        "bytes": size,
    }


@app.post("/api/session/start")
def start_session(req: SessionStartRequest):
    """Create a session and run the engagement pipeline off-thread."""
    if not req.repo_url and not req.project_path:
        raise HTTPException(400, "provide repo_url or project_path")

    session_id = uuid.uuid4().hex[:12]
    session = Session(
        session_id=session_id, source=req.source,
        repo_url=req.repo_url, project_path=req.project_path,
    )
    for k in ("project_id", "region", "service_name"):
        val = getattr(req, k)
        if val:
            session.metadata[k] = val
    REGISTRY.add(session)

    threading.Thread(target=run_pipeline, args=(session,), daemon=True).start()
    return {"session_id": session_id}


@app.get("/api/session/{session_id}/events")
async def session_events(session_id: str):
    """Server-Sent Events feed of the engagement, replayed from the start.

    Each SSE `data:` line is one event: { type, agent, message, data?, ... }.
    """
    session = _get_session_or_404(session_id)

    async def gen():
        idx = 0
        for _ in range(MAX_STREAM_POLLS):
            while idx < len(session.events):
                yield f"data: {json.dumps(session.events[idx].to_dict())}\n\n"
                idx += 1
            if session.status in TERMINAL_STATUSES:
                break
            await asyncio.sleep(STREAM_POLL_INTERVAL_S)

        # Flush any trailing events, then a sentinel so clients can close.
        while idx < len(session.events):
            yield f"data: {json.dumps(session.events[idx].to_dict())}\n\n"
            idx += 1
        yield f"data: {json.dumps({'type': 'stream_end', 'data': session.status_dict()})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/session/{session_id}/approve")
def approve_step(session_id: str, req: ApproveRequest):
    """Approve (or reject) the pending human-in-the-loop gate (e.g. deploy)."""
    session = _get_session_or_404(session_id)
    if req.approved:
        session.approve(req.step_id)
    else:
        session.reject(req.step_id)
    return {"session_id": session_id, "approved": req.approved,
            "step_id": req.step_id or (session.pending_approval or {}).get("step_id")}


@app.get("/api/session/{session_id}/status")
def session_status(session_id: str):
    """Lightweight polling: phase, readiness score, deploy URL, pending approval."""
    return _get_session_or_404(session_id).status_dict()


@app.get("/api/session/{session_id}/architecture.jpg")
def session_architecture_image(session_id: str):
    """Serve the generated architecture diagram for dashboard approval."""
    session = _get_session_or_404(session_id)
    image_path = session.metadata.get("architecture_image")
    if not image_path:
        raise HTTPException(404, "architecture diagram not available")
    path = Path(image_path)
    if not path.is_file():
        raise HTTPException(404, "architecture diagram not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/session/{session_id}/report")
def session_report(session_id: str):
    """Full engagement record for a results view."""
    s = _get_session_or_404(session_id)
    return {
        **s.status_dict(),
        "source": s.source,
        "stack": s.stack,
        "functional_gate": s.functional_gate,
        "gate": s.gate,
        "architecture": s.architecture,
        "sre_handoff": s.sre_handoff,
        "events": [e.to_dict() for e in s.events],
    }


@app.get("/")
def root():
    return {
        "name": "Prody Engine",
        "status": "ok",
        "endpoints": [
            "POST /api/upload/project",
            "GET /api/gemma/status",
            "POST /api/session/start",
            "GET /api/session/{id}/events (SSE)",
            "POST /api/session/{id}/approve",
            "GET /api/session/{id}/status",
            "GET /api/session/{id}/architecture.jpg",
            "GET /api/session/{id}/report",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
