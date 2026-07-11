/** Normalize gate summary payloads from the engine (string or severity counts). */
export function formatGateSummary(summary: unknown): string | null {
  if (!summary) return null;
  if (typeof summary === "string") return summary;
  if (typeof summary === "object" && summary !== null) {
    const counts = summary as Record<string, number>;
    if ("total" in counts || "critical" in counts) {
      const total = counts.total ?? 0;
      if (!total) return "No findings";
      const parts = (["critical", "high", "medium", "low", "info"] as const)
        .filter((k) => counts[k] > 0)
        .map((k) => `${counts[k]} ${k}`);
      return `${total} finding(s): ${parts.join(", ")}`;
    }
  }
  return String(summary);
}
