import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { getIncident } from "@/lib/incidents";
import { rollbackRemediation } from "@/lib/approvals";
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
              <RemediationListItem key={r.id} remediation={r} incidentId={data.id} />
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


type RemediationItem = {
  id: string;
  action_class: string;
  status: string;
  blast_radius: number;
  ai_confidence: number | null;
  rollback_plan: Record<string, unknown> | null;
  failure_reason: string | null;
};

function RemediationListItem({
  remediation,
  incidentId,
}: {
  remediation: RemediationItem;
  incidentId: string;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [showRollback, setShowRollback] = useState(false);
  const rollback = useMutation({
    mutationFn: () => rollbackRemediation(remediation.id, reason),
    onSuccess: () => {
      setShowRollback(false);
      setReason("");
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
    },
  });
  const canRollback =
    remediation.status === "executed" && remediation.rollback_plan;

  return (
    <li className="rounded border border-aegis-border bg-aegis-bg p-3 font-mono text-xs">
      <div className="flex items-baseline justify-between">
        <span className="text-aegis-text">{remediation.action_class}</span>
        <span className="text-aegis-muted">{remediation.status}</span>
      </div>
      <div className="mt-1 text-aegis-muted">
        blast radius {remediation.blast_radius} · ai{" "}
        {remediation.ai_confidence === null
          ? "—"
          : `${Math.round(remediation.ai_confidence * 100)}%`}{" "}
        · rollback{" "}
        {remediation.rollback_plan
          ? `→ ${(remediation.rollback_plan.action_class as string) ?? "defined"}`
          : "none"}
      </div>
      {remediation.failure_reason && (
        <div className="mt-1 text-aegis-danger">
          failure: {remediation.failure_reason}
        </div>
      )}
      {canRollback && (
        <div className="mt-2">
          {!showRollback ? (
            <button
              type="button"
              onClick={() => setShowRollback(true)}
              className="rounded border border-aegis-border px-2 py-1 text-[10px] uppercase tracking-widest text-aegis-warn hover:bg-aegis-panel"
            >
              rollback
            </button>
          ) : (
            <div className="space-y-2">
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why are you rolling this back? (audited)"
                rows={2}
                className="block w-full rounded border border-aegis-border bg-aegis-panel p-2 text-aegis-text focus:border-aegis-accent focus:outline-none"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={!reason || rollback.isPending}
                  onClick={() => rollback.mutate()}
                  className="rounded bg-aegis-warn px-3 py-1 text-aegis-bg disabled:opacity-50"
                >
                  confirm rollback
                </button>
                <button
                  type="button"
                  onClick={() => setShowRollback(false)}
                  className="rounded border border-aegis-border px-3 py-1 text-aegis-muted"
                >
                  cancel
                </button>
                {rollback.isError && (
                  <span className="text-aegis-danger">
                    {(rollback.error as Error).message}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
