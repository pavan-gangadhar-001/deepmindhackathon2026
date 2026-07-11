export function isMockSession(sessionId: string, mockFlag = false): boolean {
  return mockFlag || sessionId.startsWith("mock-");
}

export function lostSessionStatus(sessionId: string) {
  return {
    session_id: sessionId,
    phase: "error" as const,
    status: "not_found",
  };
}
