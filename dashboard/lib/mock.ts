import type { SessionEvent, SessionStatus } from "./types";

export function mockStatus(sessionId: string): SessionStatus {
  return {
    session_id: sessionId,
    phase: "security_scan",
    readiness_score: 87,
    project_path: "demo/sample-app",
  };
}

export async function* mockEventStream(
  sessionId: string
): AsyncGenerator<SessionEvent> {
  const steps: SessionEvent[] = [
    {
      type: "phase_start",
      agent: "intake",
      message: "Session started from dashboard",
      data: { session_id: sessionId, phase: "intake" },
    },
    {
      type: "phase_start",
      agent: "functional",
      message: "Starting functional gate: does the app actually work?",
      data: { phase: "functional_gate" },
    },
    {
      type: "agent_log",
      agent: "functional",
      message: "Smoke-testing routes and running the existing test suite...",
    },
    {
      type: "finding",
      agent: "functional",
      message: "Finding: /checkout returns 500 on empty cart",
      data: { title: "/checkout 500s on empty cart", severity: "medium" },
    },
    {
      type: "gate",
      agent: "functional",
      message: "Functional gate verdict: PASS_WITH_WARNINGS",
      data: {
        status: "PASS_WITH_WARNINGS",
        summary: "App boots and core flows work; 1 medium issue found.",
        gate_type: "functional",
      },
    },
    {
      type: "phase_done",
      agent: "functional",
      message: "Functional gate complete",
      data: { phase: "functional_gate" },
    },
    {
      type: "phase_start",
      agent: "security",
      message: "Starting grey-box security scan on local project...",
      data: { phase: "security_scan" },
    },
    {
      type: "agent_log",
      agent: "security",
      message: "Recon: detected Flask app, 12 routes, 2 dependencies flagged",
    },
    {
      type: "finding",
      agent: "security",
      message: "Finding: hardcoded secret key in config.py",
      data: { title: "Hardcoded secret key in config.py", severity: "high" },
    },
    {
      type: "gate",
      agent: "security",
      message: "Security gate verdict: PASS_WITH_WARNINGS",
      data: {
        status: "PASS_WITH_WARNINGS",
        summary: "No critical findings; 1 high finding needs follow-up.",
        gate_type: "security",
      },
    },
    {
      type: "phase_start",
      agent: "architect",
      message: "Planning Cloud Run deployment in asia-south1",
      data: { phase: "architect" },
    },
    {
      type: "agent_log",
      agent: "architect",
      message: "Architecture: Cloud Run + Secret Manager + Cloud Build",
    },
    {
      type: "approval_required",
      agent: "architect",
      message: "Waiting for human approval before deploying",
      data: {
        step_id: "deploy-1",
        phase: "deploy",
        description:
          "Both gates passed with warnings. Review the proposed Cloud Run architecture before deploying.",
      },
    },
    {
      type: "approved",
      agent: "architect",
      message: "Deploy approved by reviewer",
    },
    {
      type: "phase_start",
      agent: "devops",
      message: "Deploying to Cloud Run (demo mode — connect engine for live deploy)...",
      data: { phase: "deploy", mock: true },
    },
    {
      type: "phase_start",
      agent: "sre",
      message: "Confirming production health",
      data: { phase: "sre" },
    },
    {
      type: "sre_handoff",
      agent: "sre",
      message:
        "Your application is live and responding. I'm watching for errors and traffic spikes.",
      data: {
        handoff: {
          service_name: "demo-app",
          region: "asia-south1",
          deploy_url: "https://demo-app.example.run.app",
          session_id: sessionId,
        },
        health: { reachable: true, healthy: true, status_code: 200 },
      },
    },
    {
      type: "readiness",
      agent: "orchestrator",
      message: "Production readiness assessed.",
      data: { readiness_score: 87 },
    },
  ];

  for (const event of steps) {
    await new Promise((r) => setTimeout(r, 900));
    yield { ...event, timestamp: new Date().toISOString() };
  }
}
