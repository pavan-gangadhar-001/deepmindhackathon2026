"""SRE agent — post-deploy reliability check + operational handoff (C11).

After DevOps ships, the SRE agent verifies the live service is actually serving
traffic, produces the GCP context handoff payload (the shape in TASKS.md), and
explains production readiness in business terms. This is a stub in the sense
that continuous monitoring/auto-remediation is future work — but the health
check it performs is real (a live HTTP request to the deployed URL).
"""
from typing import Optional

import httpx

from engine import llm
from tools import gcloud

SYSTEM = (
    "You are the Site Reliability Engineer on an autonomous engineering team. You "
    "monitor production and keep it healthy. Report the app's live status and what "
    "you'll watch for, in short plain-language terms an owner understands."
)


def health_check(deploy_url: str, timeout: float = 15.0) -> dict:
    """Real HTTP probe of the deployed service."""
    if not deploy_url:
        return {"reachable": False, "reason": "no deploy_url"}
    try:
        r = httpx.get(deploy_url, timeout=timeout, follow_redirects=True)
        return {"reachable": True, "status_code": r.status_code,
                "healthy": r.status_code < 500}
    except httpx.HTTPError as e:
        return {"reachable": False, "reason": str(e)}


def build_handoff(session_id: str, project_id: str, service_name: str,
                  region: str, deploy_url: str) -> dict:
    """The DevOps -> SRE handoff payload (exact shape from TASKS.md)."""
    return {
        "project_id": project_id,
        "service_name": service_name,
        "region": region,
        "deploy_url": deploy_url,
        "session_id": session_id,
    }


def assess(session_id: str, deploy_result: dict) -> dict:
    """Post-deploy assessment: {handoff, health, gcp_context, explanation}."""
    deploy_url = deploy_result.get("deploy_url")
    health = health_check(deploy_url)
    handoff = build_handoff(
        session_id=session_id,
        project_id=deploy_result.get("project_id", ""),
        service_name=deploy_result.get("service_name")
                    or deploy_result.get("service", ""),
        region=deploy_result.get("region", ""),
        deploy_url=deploy_url or "",
    )
    ctx = gcloud.context()
    fallback = (
        "Your application is live and responding to requests. I'm now watching it "
        "for errors and traffic spikes, and it will scale automatically. I'll flag "
        "anything that needs your attention."
        if health.get("healthy") else
        "The application deployed, but it isn't responding healthily yet. I'm "
        "keeping watch and will help recover it."
    )
    explanation = llm.narrate(
        SYSTEM,
        f"Give the owner a short production-readiness update. Health: {health}. "
        f"Live URL: {deploy_url}.",
        fallback=fallback,
    )
    return {"handoff": handoff, "health": health, "gcp_context": ctx,
            "explanation": explanation}
