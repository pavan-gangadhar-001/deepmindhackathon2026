"""Local Gemma via Ollama — privacy-first narration for gate findings.

Used for:
  * Plain-language finding summaries (no code leaves the machine)
  * Executive gate summaries when Ollama + Gemma are available

Falls back silently to cloud Gemini (pentest reporters) or raw finding titles
when local Gemma is disabled or Ollama is not running.

Setup:
  1. Install Ollama: https://ollama.com
  2. Pull a model:  ollama pull gemma3:4b   (or gemma4 / gemma4:e4b)
  3. Set PRODY_GEMMA_ENABLED=1 in .env
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

GEMMA_ENABLED = os.getenv("PRODY_GEMMA_ENABLED", "").lower() in ("1", "true", "yes")
GEMMA_URL = os.getenv("PRODY_GEMMA_URL", "http://127.0.0.1:11434").rstrip("/")
GEMMA_MODEL = os.getenv("PRODY_GEMMA_MODEL", "gemma3:4b")
GEMMA_TIMEOUT_S = float(os.getenv("PRODY_GEMMA_TIMEOUT_S", "45"))

FINDING_SYSTEM = (
    "You translate technical software findings into plain language for a startup "
    "founder. One short sentence. No CVE IDs, no jargon. Say what is wrong and "
    "why it matters to the business."
)

EXEC_SECURITY_SYSTEM = (
    "You are a security advisor for small businesses. Given JSON findings from a "
    "real scan, write a 4-6 sentence executive summary: overall risk, the most "
    "serious issues in plain language, and whether it is safe to deploy. Use only "
    "the provided findings. No markdown headings."
)

EXEC_FUNCTIONAL_SYSTEM = (
    "You are a QA advisor. Given JSON findings from smoke tests and pytest, write "
    "a 4-6 sentence summary: does the app work, what is broken, and whether it is "
    "safe to proceed. Use only the provided findings. No markdown headings."
)


def enabled() -> bool:
    return GEMMA_ENABLED


def available() -> bool:
    """True when enabled and Ollama responds on GEMMA_URL."""
    if not enabled():
        return False
    try:
        r = httpx.get(f"{GEMMA_URL}/api/tags", timeout=2.0)
        if r.status_code != 200:
            return False
        tags = r.json().get("models", [])
        names = {m.get("name", "").split(":")[0] for m in tags}
        model_base = GEMMA_MODEL.split(":")[0]
        # Accept exact tag or any variant of the configured model family.
        return any(
            m.get("name", "") == GEMMA_MODEL
            or m.get("name", "").startswith(f"{model_base}:")
            or model_base in names
            for m in tags
        ) or bool(tags)
    except httpx.HTTPError:
        return False


def status_dict() -> dict:
    return {
        "enabled": enabled(),
        "available": available(),
        "url": GEMMA_URL,
        "model": GEMMA_MODEL,
    }


def _chat(system: str, user: str) -> str:
    r = httpx.post(
        f"{GEMMA_URL}/api/chat",
        json={
            "model": GEMMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        },
        timeout=GEMMA_TIMEOUT_S,
    )
    r.raise_for_status()
    content = r.json().get("message", {}).get("content", "")
    return (content or "").strip()


def explain_finding(finding: dict) -> Optional[str]:
    """One finding → one plain-language sentence. Returns None on failure."""
    if not available():
        return None
    payload = {
        k: finding.get(k)
        for k in ("title", "severity", "description", "evidence", "remediation", "location")
        if finding.get(k)
    }
    if not payload:
        payload = {"title": finding.get("title", "Issue")}
    try:
        return _chat(FINDING_SYSTEM, json.dumps(payload, indent=2))
    except httpx.HTTPError:
        return None


def enrich_finding(finding: dict) -> dict:
    """Return finding copy with `plain_summary` when local Gemma succeeds."""
    out = dict(finding)
    summary = explain_finding(finding)
    if summary:
        out["plain_summary"] = summary
        out["narrator"] = "gemma_local"
    return out


def executive_summary(findings: list[dict], gate_type: str = "security") -> Optional[str]:
    """Gate-level executive summary from findings JSON."""
    if not available() or not findings:
        return None
    system = EXEC_FUNCTIONAL_SYSTEM if gate_type == "functional" else EXEC_SECURITY_SYSTEM
    prompt = (
        f"Gate type: {gate_type}\nFindings (JSON):\n"
        + json.dumps(findings, indent=2)
        + "\n\nWrite the executive summary now."
    )
    try:
        return _chat(system, prompt)
    except httpx.HTTPError:
        return None


def enrich_findings(findings: list[dict]) -> list[dict]:
    return [enrich_finding(f) for f in findings]
