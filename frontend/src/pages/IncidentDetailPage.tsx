import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { getIncident } from "@/lib/incidents";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { AIReasoningPanel } from "@/components/incidents/AIReasoningPanel";

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => getIncident(id!),
    enabled: !!id,
  });

  if (isLoading) return <p className="text-sm text-aegis-muted">loading…</p>;
  if (isError)
    return (
      <p className="text-sm text-aegis-danger">
        error: {(error as Error).message}
      </p>
    );
  if (!data) return null;

  const confidence =
    data.ai_confidence === null
      ? "—"
      : `${Math.round(data.ai_confidence * 100)}%`;

  return (
    <article className="space-y-6">
      <Link
        to="/incidents"
        className="font-mono text-xs text-aegis-muted hover:text-aegis-text"
      >
        ← all incidents
      </Link>

      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <SeverityBadge severity={data.severity} />
          <span className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            {data.status}
          </span>
          <span className="font-mono text-[10px] text-aegis-muted">
            ai confidence {confidence}
          </span>
        </div>
        <h1 className="text-xl text-aegis-text">{data.title}</h1>
        {data.mitre_techniques.length > 0 && (
          <p className="font-mono text-xs text-aegis-muted">
            MITRE: {data.mitre_techniques.join(", ")}
          </p>
        )}
      </header>

      {data.summary && (
        <section className="rounded border border-aegis-border bg-aegis-bg p-4 text-sm text-aegis-text">
          {data.summary}
        </section>
      )}

      <section>
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-aegis-muted">
          ai reasoning ({data.reasoning_snapshots.length})
        </h2>
        <AIReasoningPanel snapshots={data.reasoning_snapshots} />
      </section>

      <section>
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-aegis-muted">
          remediation proposals ({data.remediation_actions.length})
        </h2>
        {data.remediation_actions.length === 0 ? (
          <p className="text-sm text-aegis-muted">
            None proposed — AI did not recommend an action.
          </p>
        ) : (
          <ul className="space-y-2">
            {data.remediation_actions.map((r) => (
              <li
                key={r.id}
                className="rounded border border-aegis-border bg-aegis-bg p-3 font-mono text-xs"
              >
                <div className="flex items-baseline justify-between">
                  <span className="text-aegis-text">{r.action_class}</span>
                  <span className="text-aegis-muted">{r.status}</span>
                </div>
                <div className="mt-1 text-aegis-muted">
                  blast radius {r.blast_radius} · ai{" "}
                  {r.ai_confidence === null
                    ? "—"
                    : `${Math.round(r.ai_confidence * 100)}%`}{" "}
                  · rollback{" "}
                  {r.rollback_plan
                    ? `→ ${(r.rollback_plan.action_class as string) ?? "defined"}`
                    : "none"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-aegis-muted">
          source alerts ({data.alerts.length})
        </h2>
        <ul className="space-y-1">
          {data.alerts.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-3 font-mono text-xs text-aegis-muted"
            >
              <SeverityBadge severity={a.severity} />
              <span className="text-aegis-text">{a.source}</span>
              <span>{a.source_event_id}</span>
              <span>{new Date(a.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
