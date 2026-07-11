import type { SreHandoff } from "@/lib/types";

export function SREPanel({
  handoff,
  health,
  explanation,
}: {
  handoff: SreHandoff | null;
  health?: { healthy?: boolean; reachable?: boolean; status_code?: number };
  explanation?: string;
}) {
  if (!handoff && !explanation) return null;

  const healthy = health?.healthy ?? false;
  const reachable = health?.reachable ?? false;

  return (
    <div className="rounded-2xl border border-hairline bg-stone p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono-label text-[12px] uppercase text-ink-muted">
            SRE · Post-deploy
          </p>
          <p className="mt-1 text-[16px] font-semibold text-ink">
            Production health check
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-[12px] font-semibold ${
            healthy
              ? "bg-enterprise-green/10 text-enterprise-green"
              : reachable
                ? "bg-amber-500/10 text-amber-700"
                : "bg-coral/10 text-coral"
          }`}
        >
          {healthy ? "HEALTHY" : reachable ? "DEGRADED" : "UNREACHABLE"}
        </span>
      </div>

      {explanation && (
        <p className="mt-3 text-[14px] leading-relaxed text-ink-muted">
          {explanation}
        </p>
      )}

      {handoff && (
        <dl className="mt-4 grid gap-2 border-t border-hairline pt-3 text-[13px]">
          {handoff.deploy_url && (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-ink-muted">Live URL</dt>
              <dd>
                <a
                  href={handoff.deploy_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-action-blue underline-offset-2 hover:underline"
                >
                  {handoff.deploy_url}
                </a>
              </dd>
            </div>
          )}
          {handoff.service_name && (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-ink-muted">Service</dt>
              <dd className="text-ink">{handoff.service_name}</dd>
            </div>
          )}
          {handoff.region && (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-ink-muted">Region</dt>
              <dd className="text-ink">{handoff.region}</dd>
            </div>
          )}
          {health?.status_code != null && (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-ink-muted">HTTP</dt>
              <dd className="text-ink">{health.status_code}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}
