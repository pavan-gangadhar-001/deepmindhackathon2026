import { API_BASE } from "./config";
import { mockEventStream, mockStatus } from "./mock";
import { isMockSession, lostSessionStatus } from "./sessionMode";
import type {
  SessionEvent,
  SessionStatus,
  StartSessionRequest,
  StartSessionResponse,
} from "./types";

export async function startSession(
  body: StartSessionRequest
): Promise<StartSessionResponse> {
  const res = await fetch(`${API_BASE}/api/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`Backend unavailable (${res.status})`);
  }

  return res.json();
}

export async function uploadProjectZip(file: File): Promise<{ project_path: string }> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/upload/project`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Upload failed (${res.status})`);
  }

  return res.json();
}

export async function getGemmaStatus(): Promise<{
  enabled: boolean;
  available: boolean;
  model: string;
}> {
  try {
    const res = await fetch(`${API_BASE}/api/gemma/status`);
    if (!res.ok) {
      return { enabled: false, available: false, model: "" };
    }
    return res.json();
  } catch {
    return { enabled: false, available: false, model: "" };
  }
}

export async function getSessionStatus(
  sessionId: string,
  options?: { mock?: boolean }
): Promise<SessionStatus> {
  const mock = isMockSession(sessionId, options?.mock);

  try {
    const res = await fetch(`${API_BASE}/api/session/${sessionId}/status`);

    if (res.status === 404) {
      return mock ? mockStatus(sessionId) : lostSessionStatus(sessionId);
    }

    if (!res.ok) {
      return mock ? mockStatus(sessionId) : lostSessionStatus(sessionId);
    }

    return res.json();
  } catch {
    return mock ? mockStatus(sessionId) : lostSessionStatus(sessionId);
  }
}

export function subscribeSessionEvents(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  options?: { mock?: boolean; onError?: (err: Error) => void }
): () => void {
  const mock = isMockSession(sessionId, options?.mock);
  const onError = options?.onError;
  let closed = false;
  let source: EventSource | null = null;
  let mockStarted = false;

  const connect = () => {
    source = new EventSource(`${API_BASE}/api/session/${sessionId}/events`);

    source.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data) as SessionEvent);
      } catch {
        onEvent({ type: "raw", message: msg.data });
      }
    };

    source.onerror = () => {
      source?.close();
      if (!closed && mock && !mockStarted) {
        mockStarted = true;
        void runMock();
      } else if (!closed && !mock) {
        onError?.(new Error("Session not found or engine restarted"));
      }
    };
  };

  const runMock = async () => {
    try {
      for await (const event of mockEventStream(sessionId)) {
        if (closed) break;
        onEvent(event);
      }
    } catch (err) {
      onError?.(err instanceof Error ? err : new Error("Stream failed"));
    }
  };

  if (mock) {
    void runMock();
  } else {
    try {
      connect();
    } catch {
      onError?.(new Error("Could not connect to engine"));
    }
  }

  return () => {
    closed = true;
    source?.close();
  };
}

export async function approveStep(
  sessionId: string,
  stepId: string,
  approved = true
): Promise<void> {
  await fetch(`${API_BASE}/api/session/${sessionId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ step_id: stepId, approved }),
  });
}
