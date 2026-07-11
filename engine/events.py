"""SSE event vocabulary shared by the engine and the dashboard.

Interface contract (TASKS.md):
    GET /api/session/{id}/events  -> SSE: { type, agent, message, data? }

Every event the orchestrator emits is one `Event`. `type` is one of `EventType`,
`agent` names the agent that produced it (so the dashboard can attribute work),
`message` is human-readable (business-first language per hackathon.md), and
`data` carries optional structured payload for the UI.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


class EventType:
    """The kinds of events the engine streams. Kept as plain strings so the
    SSE payload is trivially JSON-serialisable and language-agnostic."""

    # Lifecycle
    SESSION_START = "session_start"
    PHASE_START = "phase_start"
    PHASE_DONE = "phase_done"
    PHASE_SKIPPED = "phase_skipped"
    FINISHED = "finished"

    # Agent activity (the "live collaboration" the judges look for)
    AGENT_MESSAGE = "agent_message"   # natural-language reasoning from an agent
    TOOL_RUN = "tool_run"             # an agent invoked a local tool
    LOG = "log"                       # orchestrator progress line

    # Security gate
    FINDING = "finding"               # a security finding surfaced by the gate
    GATE = "gate"                     # the PASS/PASS_WITH_WARNINGS/FAIL verdict

    # Human-in-the-loop
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"

    # Deploy / SRE
    ARCHITECTURE_IMAGE = "architecture_image"
    DEPLOY_URL = "deploy_url"
    READINESS = "readiness"
    SRE_HANDOFF = "sre_handoff"

    # Failure
    ERROR = "error"


# Agent identities (the "engineering team").
class Agent:
    ORCHESTRATOR = "orchestrator"
    INTAKE = "intake"
    FUNCTIONAL = "functional"
    SECURITY = "security"
    ARCHITECT = "architect"
    DEVOPS = "devops"
    SRE = "sre"
    GEMMA = "gemma"  # local on-device narration (Ollama + Gemma)


@dataclass
class Event:
    type: str
    agent: str = Agent.ORCHESTRATOR
    message: str = ""
    data: Optional[dict] = None
    t: float = 0.0           # seconds since session start (set by Session.emit)
    seq: int = 0             # monotonic index (set by Session.emit)
    phase: str = ""          # phase active when emitted (set by Session.emit)

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("data") is None:
            d.pop("data")
        return d
