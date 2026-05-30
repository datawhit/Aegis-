import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { getIncident } from "@/lib/incidents";
import { rollbackRemediation } from "@/lib/approvals";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { AIReasoningPanel } from "@/components/incidents/AIReasoningPanel";

/**
 * Sprint 12: tabbed Decision Record.
 *
 * Same data flow as Sprint 9. The main column now lives inside a tab
 * container with five tabs (matches the mockup):
 *
 *   - Overview        — AI Decision Summary + Recommended Actions
 *   - AI Reasoning    — full reasoning panel (per-snapshot)
 *   - Risk & Evidence — affected entities, blast radius, MITRE
 *   - Related Alerts  — source alerts that fed this incident
 *   - Audit Trail     — link into the audit-chain explorer scoped here
 *
 * The right rail (Actions panel + Decision Attributes) is unchanged.
 */

type Tab = "overview" | "ai_reasoning" | "risk_evidence" | "related_alerts" | "audit";

const TAB_LABELS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "ai_reasoning", label: "AI Reasoning" },
  { id: "risk_evidence", label: "Risk & Evidence" },
  { id: "related_alerts", label: "Related Alerts" },
  { id: "audit", label: "Audit Trail" },
];
export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  // Sprint 13: tab state lives in `?tab=…` so a Decision Record is
  // deep-linkable (R-44). Falls back to "overview".
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab") as Tab | null;
  const validTabs: Tab[] = [
    "overview",
    "ai_reasoning",
    "risk_evidence",
    "related_alerts",
    "audit",
  ];
  const tab: Tab = tabFromUrl && validTabs.includes(tabFromUrl) ? tabFromUrl : "overview";
  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    if (next === "overview") {
      params.delete("tab");
    } else {
      params.set("tab", next);
    }
    setSearchParams(params, { replace: true });
  };

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => getIncident(id!),
    enabled: !!id,
  });

  if (isLoading) return <p className="text-sm text-aegis-muted">loading…</p>;
  if (isError)
    return (
      <p className="text-sm text-aegis-danger">error: {(error as Error).message}</p>
    );
  if (!data) return null;

  const confidence =
    data.ai_confidence === null
      ? "—"
      : `${Math.round(data.ai_confidence * 100)}%`;
  const executedAction = data.remediation_actions.find((r) => r.status === "executed");

  return (
    <div className="space-y-6">
      <Link
        to="/overview"
        className="font-mono text-xs text-aegis-muted hover:text-aegis-text"
      >
        ← back to overview
      </Link>

      {/* ─── Decision Record header ─── */}
      <header className="rounded-lg border border-aegis-border bg-aegis-panel p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
              Aegis Decision Record
            </div>
            <h1 className="mt-1 flex items-center gap-3 text-xl text-aegis-text">
              <SeverityBadge severity={data.severity} />
              {data.title}
            </h1>
            {data.mitre_techniques.length > 0 && (
              <div className="mt-2 font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
                MITRE: {data.mitre_techniques.join(", ")}
              </div>
            )}
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
              Status
            </div>
            <div
              className={`font-mono text-sm uppercase tracking-widest ${statusToneClass(
                data.status,
              )}`}
            >
              {data.status.replace(/_/g, " ")}
            </div>
            <div className="mt-1 font-mono text-[10px] text-aegis-muted">
              AI confidence: {confidence}
            </div>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        {/* ─── Main column with tabs ─── */}
        <div className="rounded-lg border border-aegis-border bg-aegis-panel">
          <nav
            role="tablist"
            className="flex flex-wrap gap-1 border-b border-aegis-border px-4 pt-3"
          >
            {TAB_LABELS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`rounded-t border-b-2 px-3 py-2 font-mono text-xs uppercase tracking-widest ${
                  tab === t.id
                    ? "border-aegis-accent text-aegis-text"
                    : "border-transparent text-aegis-muted hover:text-aegis-text"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="space-y-4 p-5">
            {tab === "overview" && (
              <>
                {data.summary && (
                  <div>
                    <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-aegis-muted">
                      AI Decision Summary
                    </h2>
                    <p className="text-sm text-aegis-text">{data.summary}</p>
                  </div>
                )}
                <div>
                  <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
                    Recommended Actions ({data.remediation_actions.length})
                  </h2>
                  {data.remediation_actions.length === 0 ? (
                    <p className="text-sm text-aegis-muted">
                      None proposed — AI did not recommend an action.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {data.remediation_actions.map((r) => (
                        <RemediationListItem
                          key={r.id}
                          remediation={r}
                          incidentId={data.id}
                        />
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}

            {tab === "ai_reasoning" && (
              <div>
                <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
                  AI Reasoning ({data.reasoning_snapshots.length})
                </h2>
                <AIReasoningPanel snapshots={data.reasoning_snapshots} />
              </div>
            )}

            {tab === "risk_evidence" && (
              <RiskEvidenceTab
                techniques={data.mitre_techniques}
                remediations={data.remediation_actions}
                aiConfidence={data.ai_confidence}
              />
            )}

            {tab === "related_alerts" && (
              <div>
                <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
                  Source Alerts ({data.alerts.length})
                </h2>
                <ul className="space-y-2">
                  {data.alerts.map((a) => (
                    <li
                      key={a.id}
                      className="flex flex-wrap items-baseline gap-3 font-mono text-xs text-aegis-muted"
                    >
                      <SeverityBadge severity={a.severity} />
                      <span className="text-aegis-text">{a.source}</span>
                      <span>{a.source_event_id}</span>
                      <span>{new Date(a.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {tab === "audit" && <AuditTab incidentId={data.id} />}
          </div>
        </div>

        {/* ─── Right rail: Actions + Attributes ─── */}
        <aside className="space-y-4">
          <ActionsPanel
            incidentId={data.id}
            executedActionId={executedAction?.id ?? null}
            canRollback={
              executedAction?.status === "executed" &&
              Boolean(executedAction?.rollback_plan)
            }
          />
          <DecisionAttributes
            severity={data.severity}
            status={data.status}
            techniques={data.mitre_techniques}
            createdAt={data.created_at}
          />
        </aside>
      </div>
    </div>
  );
}

function statusToneClass(status: string): string {
  switch (status) {
    case "escalated":
      return "text-aegis-danger";
    case "awaiting_approval":
      return "text-aegis-warn";
    case "remediating":
    case "open":
      return "text-aegis-accent";
    case "contained":
    case "closed_resolved":
      return "text-aegis-ok";
    default:
      return "text-aegis-muted";
  }
}

/* ─── Right-rail: Actions panel ─────────────────────────────── */

function ActionsPanel({
  executedActionId,
  canRollback,
  incidentId,
}: {
  executedActionId: string | null;
  canRollback: boolean;
  incidentId: string;
}) {
  return (
    <div className="rounded-lg border border-aegis-border bg-aegis-panel p-4">
      <h3 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
        Actions
      </h3>
      <div className="space-y-2">
        <Link
          to="/approvals"
          className="block rounded border border-aegis-warn bg-aegis-warn/10 px-3 py-2 text-center font-mono text-xs text-aegis-warn hover:bg-aegis-warn hover:text-aegis-bg"
        >
          Go to Review Queue
        </Link>
        {canRollback && executedActionId && (
          <RollbackButton
            actionId={executedActionId}
            incidentId={incidentId}
          />
        )}
        <button
          type="button"
          disabled
          className="block w-full cursor-not-allowed rounded border border-aegis-border bg-aegis-bg px-3 py-2 font-mono text-xs text-aegis-muted opacity-60"
        >
          Add Note (Sprint 10)
        </button>
        <button
          type="button"
          disabled
          className="block w-full cursor-not-allowed rounded border border-aegis-border bg-aegis-bg px-3 py-2 font-mono text-xs text-aegis-muted opacity-60"
        >
          Create Exception (Sprint 10)
        </button>
      </div>
    </div>
  );
}

function RollbackButton({ actionId, incidentId }: { actionId: string; incidentId: string }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [showForm, setShowForm] = useState(false);
  const mutation = useMutation({
    mutationFn: () => rollbackRemediation(actionId, reason),
    onSuccess: () => {
      setShowForm(false);
      setReason("");
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
    },
  });
  if (!showForm) {
    return (
      <button
        type="button"
        onClick={() => setShowForm(true)}
        className="block w-full rounded border border-aegis-warn px-3 py-2 font-mono text-xs text-aegis-warn hover:bg-aegis-warn hover:text-aegis-bg"
      >
        Rollback executed action
      </button>
    );
  }
  return (
    <div className="space-y-2 rounded border border-aegis-warn/40 bg-aegis-bg p-2">
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Why are you rolling this back? (audited)"
        rows={2}
        className="block w-full rounded border border-aegis-border bg-aegis-panel p-2 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!reason || mutation.isPending}
          onClick={() => mutation.mutate()}
          className="flex-1 rounded bg-aegis-warn px-3 py-1.5 font-mono text-xs text-aegis-bg disabled:opacity-50"
        >
          confirm
        </button>
        <button
          type="button"
          onClick={() => setShowForm(false)}
          className="rounded border border-aegis-border px-3 py-1.5 font-mono text-xs text-aegis-muted"
        >
          cancel
        </button>
      </div>
      {mutation.isError && (
        <p className="font-mono text-[10px] text-aegis-danger">
          {(mutation.error as Error).message}
        </p>
      )}
    </div>
  );
}

function DecisionAttributes({
  severity,
  status,
  techniques,
  createdAt,
}: {
  severity: string;
  status: string;
  techniques: string[];
  createdAt: string;
}) {
  return (
    <div className="rounded-lg border border-aegis-border bg-aegis-panel p-4">
      <h3 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
        Decision Attributes
      </h3>
      <dl className="grid grid-cols-[110px_1fr] gap-y-2 font-mono text-xs">
        <dt className="text-aegis-muted">severity</dt>
        <dd className="text-aegis-text">{severity}</dd>
        <dt className="text-aegis-muted">status</dt>
        <dd className="text-aegis-text">{status}</dd>
        <dt className="text-aegis-muted">created</dt>
        <dd className="text-aegis-text">{new Date(createdAt).toLocaleString()}</dd>
        {techniques.length > 0 && (
          <>
            <dt className="text-aegis-muted">mitre</dt>
            <dd className="text-aegis-text">{techniques.join(", ")}</dd>
          </>
        )}
      </dl>
    </div>
  );
}

/* ─── Remediation list item (unchanged data flow, lighter chrome) ─── */

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
}: {
  remediation: RemediationItem;
  incidentId: string;
}) {
  return (
    <li className="rounded border border-aegis-border bg-aegis-bg p-3 font-mono text-xs">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-aegis-accent">{remediation.action_class}</span>
        <span className="rounded bg-aegis-panel px-2 py-0.5 text-[10px] uppercase tracking-widest text-aegis-muted">
          {remediation.status}
        </span>
      </div>
      <div className="mt-1 text-aegis-muted">
        blast radius {remediation.blast_radius} · AI{" "}
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
    </li>
  );
}

/* ─── Tab: Risk & Evidence ──────────────────────────────────── */

function RiskEvidenceTab({
  techniques,
  remediations,
  aiConfidence,
}: {
  techniques: string[];
  remediations: RemediationItem[];
  aiConfidence: number | null;
}) {
  const totalBlast = remediations.reduce((acc, r) => acc + (r.blast_radius || 0), 0);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Risk Signals
        </h2>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Metric label="AI Confidence" value={
            aiConfidence === null ? "—" : `${Math.round(aiConfidence * 100)}%`
          } />
          <Metric label="Total Blast Radius" value={totalBlast.toString()} />
          <Metric
            label="MITRE Techniques"
            value={techniques.length === 0 ? "—" : techniques.join(", ")}
          />
        </dl>
      </div>

      <div>
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Why Aegis Could Act
        </h2>
        <ul className="space-y-2 text-sm text-aegis-text">
          {(aiConfidence ?? 0) >= 0.85 ? (
            <li>
              <Check /> AI confidence ({Math.round((aiConfidence ?? 0) * 100)}%) exceeds
              autonomy threshold (85%).
            </li>
          ) : (
            <li>
              <Cross /> AI confidence below 85% — outside Aegis's autonomy window.
            </li>
          )}
          {remediations.every((r) => r.rollback_plan) ? (
            <li>
              <Check /> Every proposed action carries a rollback plan.
            </li>
          ) : (
            <li>
              <Cross /> One or more actions lack a rollback plan; Aegis cannot act
              autonomously on them.
            </li>
          )}
          {totalBlast <= 5 ? (
            <li>
              <Check /> Total blast radius ({totalBlast}) is within policy bounds.
            </li>
          ) : (
            <li>
              <Cross /> Total blast radius ({totalBlast}) exceeds the standard policy
              cap of 5.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-aegis-border bg-aegis-bg p-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </div>
      <div className="mt-1 text-sm text-aegis-text">{value}</div>
    </div>
  );
}

function Check() {
  return <span className="mr-2 text-aegis-ok">✓</span>;
}

function Cross() {
  return <span className="mr-2 text-aegis-danger">✗</span>;
}

/* ─── Tab: Audit Trail (deep-link into the explorer) ─────────── */

function AuditTab({ incidentId }: { incidentId: string }) {
  return (
    <div className="space-y-3">
      <h2 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
        Audit Trail
      </h2>
      <p className="text-sm text-aegis-muted">
        Aegis writes every decision affecting this incident to the hash-chained
        audit log. View the full trail in the dedicated explorer.
      </p>
      <div className="rounded border border-aegis-border bg-aegis-bg p-3 font-mono text-xs text-aegis-muted">
        <div>resource_type: <span className="text-aegis-accent">incident</span></div>
        <div>resource_id: <span className="text-aegis-accent">{incidentId}</span></div>
      </div>
      <Link
        to={`/audit-logs?resource_type=incident&resource_id=${incidentId}`}
        className="inline-block rounded border border-aegis-accent px-3 py-1.5 font-mono text-xs text-aegis-accent hover:bg-aegis-accent hover:text-aegis-bg"
      >
        Open in Audit Trail explorer →
      </Link>
    </div>
  );
}
