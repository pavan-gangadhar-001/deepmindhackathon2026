"""Session state for one end-to-end engagement (code -> production).

A `Session` is the shared, mutable record the orchestrator writes to and the
FastAPI endpoints read from. It mirrors the pentest agent's `EngagementState`:
the orchestrator runs on a background thread and appends `Event`s; the SSE
endpoint tails `events`; polling reads `phase`/`status`.

Human-in-the-loop approval is built in: critical actions (deploy) call
`request_approval(...)`, which blocks the orchestrator thread on a
`threading.Event` until `approve(step_id)` is called via the API.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .events import Event, EventType, Agent

# Ordered phases of the engagement (matches Interface Contract in TASKS.md).
PHASES = ("intake", "functional_gate", "security_scan", "architect", "deploy", "sre")

# Statuses that mean "nothing more will change".
TERMINAL_STATUSES = ("done", "error", "cancelled")


@dataclass
class Session:
    session_id: str
    source: str = "dashboard"        # "ide" | "dashboard"
    repo_url: Optional[str] = None
    project_path: Optional[str] = None

    phase: str = "queued"
    status: str = "queued"           # queued|running|awaiting_approval|done|error|cancelled

    # Results surfaced to the dashboard.
    stack: Optional[dict] = None
    functional_gate: Optional[dict] = None  # functest verdict payload
    gate: Optional[dict] = None      # pentest verdict payload
    architecture: Optional[dict] = None
    deploy_url: Optional[str] = None
    readiness_score: Optional[int] = None
    sre_handoff: Optional[dict] = None

    # Event stream + bookkeeping.
    events: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    cancelled: bool = False

    # Human-in-the-loop approval machinery.
    pending_approval: Optional[dict] = None      # {step_id, phase, description}
    _approved_steps: set = field(default_factory=set)
    _rejected_steps: set = field(default_factory=set)
    _approval_gate: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ---- event emission -------------------------------------------------
    def emit(self, type: str, agent: str = Agent.ORCHESTRATOR,
             message: str = "", data: Optional[dict] = None) -> Event:
        """Append an event to the stream (thread-safe)."""
        if type == EventType.PHASE_START and isinstance(data, dict) and data.get("phase"):
            self.phase = data["phase"]
        with self._lock:
            ev = Event(
                type=type, agent=agent, message=message, data=data,
                t=round(time.time() - self.started_at, 2),
                seq=len(self.events), phase=self.phase,
            )
            self.events.append(ev)
        return ev

    def emit_phase_start(self, phase: str, message: str = "") -> Event:
        self.phase = phase
        return self.emit(EventType.PHASE_START, message=message or f"Starting {phase}",
                         data={"phase": phase})

    def emit_phase_done(self, phase: str, message: str = "") -> Event:
        return self.emit(EventType.PHASE_DONE, message=message or f"Finished {phase}",
                         data={"phase": phase})

    # ---- human-in-the-loop approval ------------------------------------
    def request_approval(self, step_id: str, description: str,
                         data: Optional[dict] = None, timeout: float = 900.0) -> bool:
        """Block the orchestrator until the user approves/rejects `step_id`.

        Returns True if approved, False if rejected or timed out. Emits an
        `approval_required` event the dashboard renders as a confirm gate.
        """
        if step_id in self._approved_steps:
            return True
        payload = {"step_id": step_id, "phase": self.phase, "description": description}
        if data:
            payload.update(data)
        self.pending_approval = payload
        self.status = "awaiting_approval"
        self._approval_gate.clear()
        self.emit(EventType.APPROVAL_REQUIRED, message=description, data=payload)

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.cancelled:
                return False
            if step_id in self._approved_steps:
                self._settle_approval()
                return True
            if step_id in self._rejected_steps:
                self._settle_approval()
                return False
            self._approval_gate.wait(timeout=0.5)
        # Timed out: fail closed (no silent deploy).
        self._settle_approval()
        self.emit(EventType.LOG, message=f"Approval for '{step_id}' timed out.")
        return False

    def _settle_approval(self) -> None:
        self.pending_approval = None
        if self.status == "awaiting_approval":
            self.status = "running"

    def approve(self, step_id: Optional[str] = None) -> None:
        """Mark a pending step approved (called by the API)."""
        sid = step_id or (self.pending_approval or {}).get("step_id")
        if sid:
            self._approved_steps.add(sid)
            self.emit(EventType.APPROVED, message=f"Approved: {sid}", data={"step_id": sid})
        self._approval_gate.set()

    def reject(self, step_id: Optional[str] = None) -> None:
        sid = step_id or (self.pending_approval or {}).get("step_id")
        if sid:
            self._rejected_steps.add(sid)
            self.emit(EventType.LOG, message=f"Rejected: {sid}", data={"step_id": sid})
        self._approval_gate.set()

    # ---- status snapshot ------------------------------------------------
    @staticmethod
    def _display_summary(gate: dict) -> Optional[str]:
        if gate.get("executive_summary"):
            return str(gate["executive_summary"])
        summary = gate.get("summary")
        if isinstance(summary, str):
            return summary
        if isinstance(summary, dict):
            total = summary.get("total", 0)
            if not total:
                return "No findings"
            parts = [
                f"{summary[k]} {k}"
                for k in ("critical", "high", "medium", "low", "info")
                if summary.get(k)
            ]
            return f"{total} finding(s): " + ", ".join(parts)
        return None

    @staticmethod
    def _gate_verdict(gate: Optional[dict], gate_type: str) -> Optional[dict]:
        if not gate:
            return None
        status = gate.get("status")
        if not status:
            return None
        return {
            "status": status,
            "summary": Session._display_summary(gate),
            "gate_type": gate_type,
        }

    def status_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "phase": self.phase,
            "status": self.status,
            "readiness_score": self.readiness_score,
            "deploy_url": self.deploy_url,
            "functional_gate_status": self._gate_verdict(
                self.functional_gate, "functional"
            ),
            "gate_status": self._gate_verdict(self.gate, "security"),
            "pending_approval": self.pending_approval,
            "sre_handoff": self.sre_handoff,
            "events_count": len(self.events),
        }


class SessionRegistry:
    """Thread-safe in-memory store of active sessions."""

    def __init__(self):
        self._sessions: dict = {}
        self._lock = threading.Lock()

    def add(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def all(self) -> list:
        with self._lock:
            return list(self._sessions.values())


REGISTRY = SessionRegistry()
