"""Session-aware bridge from the Prody engine to the managed-agent deploy flow.

Wraps deploy_agent.managed_deploy (teammate's working MCP deploy agent) so the
orchestrator can run:

    architect (plan + diagram) -> dashboard approval -> MCP deploy -> deploy URL
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from agents import devops as devops_agent
from engine.events import Agent, EventType
from engine.session import Session
from tools import gcloud

_DEPLOY_URL_RE = re.compile(
    r"https://[^\s\)\]\"'<>]+",
    re.IGNORECASE,
)

ARCHITECT_INSTRUCTIONS = (
    "You are a Cloud Architect specialized strictly in designing GCP cloud architectures. "
    "The orchestrator has already provided the local application directory and stack summary. "
    "When the application is copied to /workspace/application, run "
    "`python /workspace/.app-transfer/restore.py`, inspect the app in the sandbox, "
    "design an appropriate GCP architecture, and explain it clearly.\n"
    "ALWAYS generate a visual architecture diagram by calling generate_architecture_image. "
    "The prompt must list ONLY the GCP services used and how they connect.\n"
    "After the diagram is generated, summarize the architecture for human approval."
)

DEVOPS_INSTRUCTIONS = (
    "You are a Senior DevOps Managed Agent strictly specialized in autonomously executing GCP deployments. "
    "You receive an approved architecture from the Cloud Architect. "
    "When the orchestrator says the application was copied into the sandbox, restore it "
    "immediately, detect the sandbox OS and available tools, and use /workspace/application "
    "as the source directory.\n"
    "Use google_cloud_resource_manager MCP to inspect projects. Create/bill projects with "
    "create_gcp_project when needed (default billing account: 019B50-4CED52-737F15).\n"
    "Enable APIs with enable_apis. ALWAYS use google_cloud_run MCP for Cloud Run deployment. "
    "Use google_cloud_storage MCP for buckets. Use deploy_infrastructure only for unsupported services.\n"
    "A deployment is not successful until get_service reports Ready. Remediate failures autonomously.\n"
    "Never print manual shell commands. Your final response must include the live production URL."
)


def is_available() -> bool:
    try:
        from deploy_agent import managed_deploy as md

        md.ensure_client()
        return bool(md.GCLOUD_BIN)
    except Exception:
        return False


def _artifacts_dir(session: Session) -> Path:
    root = Path(__file__).resolve().parent.parent / "artifacts" / session.session_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def _wrap_handlers(handlers: dict, session: Session, agent: str) -> dict:
    def wrap(name: str, fn: Callable):
        def wrapped(**arguments):
            session.emit(
                EventType.TOOL_RUN,
                agent=agent,
                message=f"Running: {name}",
                data={"tool": name, "args": arguments},
            )
            return fn(**arguments)

        return wrapped

    return {name: wrap(name, fn) for name, fn in handlers.items()}


def _extract_deploy_url(text: str) -> Optional[str]:
    if not text:
        return None
    for match in _DEPLOY_URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;")
        lowered = url.lower()
        if any(
            token in lowered
            for token in ("run.app", "cloudfunctions.net", "appspot.com", "googleusercontent.com")
        ):
            return url
    return None


def run_architect_phase(session: Session) -> bool:
    """Managed-agent architect: inspect app, plan, generate architecture.jpg."""
    from deploy_agent import managed_deploy as md

    md.ensure_client()
    project_path = session.project_path
    if not project_path:
        session.emit(
            EventType.ERROR,
            agent=Agent.ARCHITECT,
            message="No application path available for architecture design.",
        )
        return False

    md.ACTIVE_APPLICATION_DIRECTORY = project_path
    image_path = _artifacts_dir(session) / "architecture.jpg"
    md.set_architecture_output_path(image_path)

    app_env = md.build_application_environment(project_path)
    stack = session.stack or {}
    gate = session.gate or {}
    kickoff = md.application_transfer_prompt(
        "Design the production GCP architecture for this application.\n"
        f"Local path (already registered): {project_path}\n"
        f"Detected stack: {stack}\n"
        f"Security gate verdict: {gate.get('status', 'unknown')}\n"
        f"Security summary: {gate.get('summary') or gate.get('executive_summary') or 'n/a'}"
    )

    architect_handlers = _wrap_handlers(
        {"generate_architecture_image": md.generate_architecture_image},
        session,
        Agent.ARCHITECT,
    )

    try:
        response = md.run_managed_agent(
            kickoff,
            ARCHITECT_INSTRUCTIONS,
            md.ARCHITECT_TOOLS,
            architect_handlers,
            environment=app_env,
        )
    except Exception as exc:
        session.emit(
            EventType.ERROR,
            agent=Agent.ARCHITECT,
            message=f"Architecture design failed: {exc}",
        )
        return False

    output = response.output_text or ""
    session.metadata["architect_interaction_id"] = response.id
    session.metadata["architect_history"] = [f"Architect: {output}"]
    session.architecture = {
        "plan": {"summary": output[:4000]},
        "explanation": output,
        "managed_agent": True,
    }

    session.emit(
        EventType.AGENT_MESSAGE,
        agent=Agent.ARCHITECT,
        message=output,
        data={"plan": session.architecture["plan"]},
    )

    if image_path.is_file():
        image_url = f"/api/session/{session.session_id}/architecture.jpg"
        session.metadata["architecture_image"] = str(image_path)
        session.emit(
            EventType.ARCHITECTURE_IMAGE,
            agent=Agent.ARCHITECT,
            message="Architecture diagram ready for your review.",
            data={"image_url": image_url},
        )

    approved = session.request_approval(
        step_id="architecture",
        description=(
            "Review the proposed GCP architecture and diagram. "
            "Approve to start the real MCP deployment."
        ),
        data={
            "architecture": session.architecture.get("plan"),
            "image_url": (
                f"/api/session/{session.session_id}/architecture.jpg"
                if image_path.is_file()
                else None
            ),
        },
    )
    if not approved:
        session.emit(
            EventType.LOG,
            agent=Agent.ARCHITECT,
            message="Architecture was not approved — deployment will not start.",
        )
        return False
    return True


def run_deploy_phase(session: Session) -> bool:
    """Managed-agent DevOps: MCP deploy after architecture approval."""
    from deploy_agent import managed_deploy as md

    md.ensure_client()
    project_path = session.project_path
    if not project_path:
        session.emit(
            EventType.ERROR,
            agent=Agent.DEVOPS,
            message="No application path available for deployment.",
        )
        return False

    md.ACTIVE_APPLICATION_DIRECTORY = project_path
    app_env = md.build_application_environment(project_path)
    history = session.metadata.get("architect_history") or []
    context = "\n".join(history)

    mcp_project = (
        session.metadata.get("project_id")
        or __import__("os").environ.get("GOOGLE_CLOUD_MCP_PROJECT")
        or md.extract_project_id(context)
    )
    if not mcp_project:
        try:
            configured = md._gcloud_output("config", "get-value", "project")
            if configured and configured != "(unset)":
                mcp_project = configured.strip()
        except Exception:
            pass
    if not mcp_project:
        session.emit(
            EventType.ERROR,
            agent=Agent.DEVOPS,
            message=(
                "No Google Cloud project configured. Set project_id on session start, "
                "run `gcloud config set project <id>`, or set GOOGLE_CLOUD_MCP_PROJECT."
            ),
        )
        return False

    session.metadata["project_id"] = mcp_project

    service_name = (
        session.metadata.get("service_name")
        or devops_agent.service_name_for(project_path)
    )
    region = session.metadata.get("region") or gcloud.DEFAULT_REGION

    # Human-in-the-loop: deploys are a critical action (context.md — Human Approval).
    # Mirrors the legacy gcloud path in engine/orchestrator.py::_phase_deploy — the
    # managed-MCP path must gate on the same dashboard/IDE approval before it
    # performs a real Cloud Run deployment.
    approved = session.request_approval(
        step_id="deploy",
        description=(f"Ready to deploy '{service_name}' to Google Cloud Run "
                     f"in project {mcp_project}. Approve to go live in production."),
        data={"project_id": mcp_project, "service_name": service_name,
              "region": region, "architecture": (session.architecture or {}).get("plan")},
    )
    if not approved:
        session.emit(EventType.LOG, agent=Agent.DEVOPS,
                     message="Deployment was not approved — nothing was changed in production.")
        return False

    try:
        devops_tools = [*md.DEVOPS_TOOLS, *md.build_google_cloud_mcp_tools(mcp_project)]
    except Exception as exc:
        session.emit(
            EventType.ERROR,
            agent=Agent.DEVOPS,
            message=f"Google Cloud MCP configuration failed: {exc}",
        )
        return False

    devops_handlers = _wrap_handlers(
        {
            "create_gcp_project": md.create_gcp_project,
            "enable_apis": md.enable_apis,
            "upload_application_archive": md.upload_application_archive,
            "read_cloud_run_logs": md.read_cloud_run_logs,
            "build_application_image": md.build_application_image,
            "deploy_infrastructure": md.deploy_infrastructure,
        },
        session,
        Agent.DEVOPS,
    )

    handoff = (
        "The user approved the architecture in the dashboard. Deploy it to production now.\n"
        "The complete local application has been copied into this sandbox. First run "
        "`python /workspace/.app-transfer/restore.py`, then deploy from "
        f"`{md.SANDBOX_APPLICATION_DIR}`.\n\n"
        f"--- ARCHITECT CONTEXT ---\n{context}"
    )

    session.emit(
        EventType.AGENT_MESSAGE,
        agent=Agent.DEVOPS,
        message=f"Deploying to Google Cloud project {mcp_project} via Managed Agents + MCP.",
        data={"project_id": mcp_project},
    )

    try:
        response = md.run_managed_agent(
            handoff,
            DEVOPS_INSTRUCTIONS,
            devops_tools,
            devops_handlers,
            environment=app_env,
        )
    except Exception as exc:
        session.emit(
            EventType.ERROR,
            agent=Agent.DEVOPS,
            message=f"Deployment failed: {exc}",
        )
        return False

    output = response.output_text or ""
    session.metadata["devops_interaction_id"] = response.id
    session.metadata["deploy_result"] = {
        "ok": True,
        "output": output,
        "managed_agent": True,
        "deploy_url": deploy_url,
        "project_id": session.metadata.get("project_id"),
        "service": session.metadata.get("service_name"),
        "region": session.metadata.get("region"),
    }

    deploy_url = _extract_deploy_url(output)
    session.emit(
        EventType.AGENT_MESSAGE,
        agent=Agent.DEVOPS,
        message=output or "Deployment finished.",
        data={"output": output[:4000]},
    )

    if deploy_url:
        session.deploy_url = deploy_url
        session.emit(
            EventType.DEPLOY_URL,
            agent=Agent.DEVOPS,
            message=f"Your application is live at {deploy_url}",
            data={"deploy_url": deploy_url},
        )
        return True

    session.emit(
        EventType.ERROR,
        agent=Agent.DEVOPS,
        message=(
            "Deployment completed but no production URL was found in the agent response. "
            "Check the event log for tool output."
        ),
        data={"output": output[-2000:]},
    )
    return False
