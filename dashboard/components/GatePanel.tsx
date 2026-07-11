import type { Finding, GateVerdict } from "@/lib/types";
import { formatGateSummary } from "@/lib/gateSummary";

const STATUS_STYLES: Record<string, { pill: string; label: string }> = {
  PASS: { pill: "bg-enterprise-green/10 text-enterprise-green", label: "PASS" },
  PASS_WITH_WARNINGS: {
    pill: "bg-amber-500/10 text-amber-700",
    label: "WARN",
  },
  FAIL: { pill: "bg-coral/10 text-coral", label: "FAIL" },
  ERROR: { pill: "bg-red-600/10 text-red-600", label: "ERROR" },
};

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-600/10 text-red-600",
  high: "bg-coral/10 text-coral",
  medium: "bg-amber-500/10 text-amber-700",
  low: "bg-action-blue/10 text-action-blue",
  info: "bg-canvas text-ink-muted",
};

function GateBadge({
  label,
  question,
  verdict,
  findings,
}: {
  label: string;
  question: string;
  verdict: GateVerdict | null | undefined;
  findings: Finding[];
}) {
  const status = verdict?.status;
  const style = status ? STATUS_STYLES[status] : undefined;
  const summaryText = formatGateSummary(verdict?.summary);

  return (
    <div className="rounded-2xl border border-hairline bg-stone p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono-label text-[12px] uppercase text-ink-muted">
            {label}
          </p>
          <p className="mt-1 text-[16px] font-semibold text-ink">
            {question}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-[12px] font-semibold ${
            style ? style.pill : "bg-canvas text-ink-muted"
          }`}
        >
          {style ? style.label : (status ?? "PENDING")}
        </span>
      </div>

      {summaryText && (
        <p className="mt-3 text-[13px] leading-relaxed text-ink-muted">
          {summaryText}
        </p>
      )}

      {findings.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-hairline pt-3">
          {findings.map((finding, i) => (
            <li
              key={`${finding.title}-${i}`}
              className="border-b border-hairline/60 pb-2 last:border-0 last:pb-0"
            >
              <div className="flex items-start justify-between gap-3 text-[13px] text-ink">
                <span className="min-w-0">
                  {finding.plain_summary ?? finding.title}
                </span>
                {finding.severity && (
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${
                      SEVERITY_STYLES[String(finding.severity).toLowerCase()] ??
                      "bg-canvas text-ink-muted"
                    }`}
                  >
                    {String(finding.severity)}
                  </span>
                )}
              </div>
              {finding.plain_summary && finding.title !== finding.plain_summary && (
                <p className="mt-1 text-[11px] text-ink-muted">{finding.title}</p>
              )}
              {finding.narrator === "gemma_local" && (
                <p className="mt-1 text-[10px] uppercase tracking-wide text-action-blue">
                  On-device · Gemma
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function GatePanel({
  functional,
  security,
  functionalFindings,
  securityFindings,
}: {
  functional: GateVerdict | null;
  security: GateVerdict | null;
  functionalFindings: Finding[];
  securityFindings: Finding[];
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <GateBadge
        label="Functional gate"
        question="Works?"
        verdict={functional}
        findings={functionalFindings}
      />
      <GateBadge
        label="Security gate"
        question="Secure?"
        verdict={security}
        findings={securityFindings}
      />
    </div>
  );
}
