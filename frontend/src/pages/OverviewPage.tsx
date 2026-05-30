import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import { getOverview, type OvernightSummary, type TrustScore } from "@/lib/overview";
import { listActionsFeed, type ActionFeedItem, type ActionOutcome } from "@/lib/actions";
import { AegisAssistantPanel } from "@/components/assistant/AegisAssistantPanel";

/**
 * Sprint 9: the operator-first landing page.
 *
 * The hierarchy is intentional — Aegis-first, incidents-second:
 *   1. Personalized "what Aegis accomplished" greeting
 *   2. Overnight Summary KPI strip
 *   3. Aegis Trust Score panel
 *   4. Aegis Actions Feed (centerpiece, tabbed by outcome)
 *   5. Requires Your Attention strip
 *   6. Top Active Policies sidebar
 *   7. Aegis Assistant shell (BETA — input only, suggested queries)
 *
 * Sprint 11 deepens "Recent Risk Reduction" + Risk Categories.
 * Sprint 10 wires the Assistant chat backend.
 */

export default function OverviewPage() {
  const user = useAuthStore((s) => s.user);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["overview"],
    queryFn: getOverview,
    refetchInterval: 30_000,
  });

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <Greeting userName={user?.display_name || user?.email || "operator"} />

      {isLoading || !overview ? (
        <div className="rounded border border-aegis-border bg-aegis-panel p-6 text-sm text-aegis-muted">
          Loading the overnight summary…
        </div>
      ) : (
        <>
          <OvernightStrip summary={overview.overnight_summary} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_280px]">
            <TrustScoreCard score={overview.trust_score} />
            <RiskSnapshotCard
              score={overview.risk_snapshot.score}
              label={overview.risk_snapshot.label}
              deltaPct={overview.risk_snapshot.delta_pct}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
            <ActionsFeedPanel />
            <TopPoliciesPanel policies={overview.top_policies_24h} />
          </div>

          <RequiresAttentionRow attention={overview.requires_attention} />

          <AegisAssistantPanel />
        </>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────── */

function Greeting({ userName }: { userName: string }) {
  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 5) return "Working late";
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  }, []);
  return (
    <header>
      <h1 className="text-2xl font-semibold text-aegis-text">
        {greeting}, {userName.split("@")[0]} <span aria-hidden>☀</span>
      </h1>
      <p className="mt-1 font-mono text-xs uppercase tracking-widest text-aegis-muted">
        Here&apos;s what Aegis accomplished while you were away.
      </p>
    </header>
  );
}

/* ─── Overnight KPI strip ─────────────────────────────────────── */

function OvernightStrip({ summary }: { summary: OvernightSummary }) {
  const tiles = [
    {
      label: "Issues Evaluated",
      value: summary.issues_evaluated.toLocaleString(),
      tone: "neutral" as const,
    },
    {
      label: "Resolved Autonomously",
      value: summary.resolved_autonomously.toLocaleString(),
      sub: pctTag(summary, "resolved_autonomously"),
      tone: "ok" as const,
    },
    {
      label: "Stabilized",
      value: summary.stabilized.toLocaleString(),
      tone: "warn" as const,
    },
    {
      label: "Escalated",
      value: summary.escalated.toLocaleString(),
      tone: "danger" as const,
    },
    {
      label: "Analyst Hours Saved",
      value: summary.analyst_hours_saved.toFixed(1),
      tone: "accent" as const,
    },
    {
      label: "Mean Response Time",
      value:
        summary.mean_response_time_seconds === null
          ? "—"
          : `${Math.round(summary.mean_response_time_seconds)}s`,
      tone: "accent" as const,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map((t) => (
        <KpiTile key={t.label} {...t} />
      ))}
    </div>
  );
}

function pctTag(s: OvernightSummary, field: keyof OvernightSummary) {
  const fieldKey =
    field === "resolved_autonomously" ? "resolved" : (field as string);
  const v = s.deltas?.[fieldKey];
  if (v === undefined) return undefined;
  if (v === 0) return "= 0%";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}% vs yesterday`;
}

function KpiTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone: "neutral" | "ok" | "warn" | "danger" | "accent";
}) {
  const toneClass = {
    neutral: "text-aegis-text",
    ok: "text-aegis-ok",
    warn: "text-aegis-warn",
    danger: "text-aegis-danger",
    accent: "text-aegis-accent",
  }[tone];
  return (
    <div className="rounded-lg border border-aegis-border bg-aegis-panel p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</div>
      {sub && (
        <div className="mt-1 font-mono text-[10px] text-aegis-muted">{sub}</div>
      )}
    </div>
  );
}

/* ─── Trust Score ─────────────────────────────────────────────── */

function TrustScoreCard({ score }: { score: TrustScore }) {
  const labelClass = {
    Excellent: "bg-aegis-ok/20 text-aegis-ok",
    Good: "bg-aegis-accent/20 text-aegis-accent",
    Fair: "bg-aegis-warn/20 text-aegis-warn",
    Poor: "bg-aegis-danger/20 text-aegis-danger",
  }[score.label];
  return (
    <div className="rounded-lg border border-aegis-border bg-aegis-panel p-5">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <div className="flex items-center gap-4">
          <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-aegis-ok/40">
            <div className="text-center">
              <div className="text-2xl font-semibold text-aegis-text">
                {score.score}
              </div>
              <div className="font-mono text-[9px] uppercase text-aegis-muted">/100</div>
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-aegis-text">
                Aegis Trust Score
              </h2>
              <span
                className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${labelClass}`}
              >
                {score.label}
              </span>
            </div>
            <p className="mt-1 text-sm text-aegis-muted">
              High policy adherence and successful autonomous operations.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 sm:ml-auto">
          <SubMetric label="Rollbacks" value={score.rollbacks_24h.toString()} period="Last 24h" />
          <SubMetric
            label="Policy Adherence"
            value={`${score.policy_adherence_pct_7d.toFixed(1)}%`}
            period="Last 7 days"
          />
          <SubMetric
            label="Rollback Rate"
            value={`${score.rollback_rate_pct_30d.toFixed(1)}%`}
            period="Last 30 days"
          />
        </div>
      </div>
    </div>
  );
}

function SubMetric({ label, value, period }: { label: string; value: string; period: string }) {
  return (
    <div>
      <div className="text-lg font-semibold text-aegis-text">{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </div>
      <div className="font-mono text-[9px] text-aegis-muted">{period}</div>
    </div>
  );
}

/* ─── Risk Snapshot (single-scalar v1; trend chart in Sprint 11) ─ */

function RiskSnapshotCard({
  score,
  label,
  deltaPct,
}: {
  score: number;
  label: "Low" | "Medium" | "High" | "Critical";
  deltaPct: number | null;
}) {
  const tone =
    label === "Low"
      ? "text-aegis-ok"
      : label === "Medium"
        ? "text-aegis-warn"
        : "text-aegis-danger";
  return (
    <div className="flex flex-col rounded-lg border border-aegis-border bg-aegis-panel p-5">
      <h3 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
        Risk Snapshot
      </h3>
      <div className="mt-3 flex items-baseline gap-2">
        <span className={`text-4xl font-semibold ${tone}`}>{score}</span>
        <span className="font-mono text-xs text-aegis-muted">/100</span>
        <span
          className={`ml-2 rounded px-2 py-0.5 font-mono text-[10px] uppercase ${tone} bg-current/10`}
        >
          {label}
        </span>
      </div>
      <div className="mt-2 font-mono text-[10px] text-aegis-muted">
        {deltaPct === null
          ? "No prior window to compare"
          : `${deltaPct > 0 ? "↑" : "↓"} ${Math.abs(deltaPct).toFixed(1)}% vs yesterday`}
      </div>
      <Link
        to="/risk-analytics"
        className="mt-auto pt-4 font-mono text-[10px] uppercase tracking-widest text-aegis-accent hover:underline"
      >
        Open Risk Analytics →
      </Link>
    </div>
  );
}

/* ─── Aegis Actions Feed (centerpiece) ──────────────────────────── */

function ActionsFeedPanel() {
  const [tab, setTab] = useState<"all" | ActionOutcome>("all");
  const { data, isLoading } = useQuery({
    queryKey: ["actions-feed", tab],
    queryFn: () => listActionsFeed({ status: tab, limit: 25 }),
    refetchInterval: 15_000,
  });

  return (
    <section className="rounded-lg border border-aegis-border bg-aegis-panel">
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-aegis-border px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-aegis-text">Aegis Actions Feed</h2>
          <p className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            Real-time log of actions taken by Aegis
          </p>
        </div>
        <nav className="flex overflow-hidden rounded border border-aegis-border font-mono text-xs">
          {(["all", "resolved", "stabilized", "escalated"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 ${
                tab === t
                  ? "bg-aegis-accent text-aegis-bg"
                  : "text-aegis-muted hover:text-aegis-text"
              }`}
            >
              {t} {data && <span className="opacity-60">({data.counts[t] ?? 0})</span>}
            </button>
          ))}
        </nav>
      </header>
      {isLoading && (
        <div className="p-5 text-sm text-aegis-muted">Loading actions…</div>
      )}
      {data?.items.length === 0 && (
        <div className="p-5 text-sm text-aegis-muted">
          No actions in this window yet. Aegis will fill this feed as
          alerts come in.
        </div>
      )}
      <ul className="divide-y divide-aegis-border">
        {data?.items.map((item) => <ActionFeedRow key={item.action_id} item={item} />)}
      </ul>
    </section>
  );
}

function ActionFeedRow({ item }: { item: ActionFeedItem }) {
  const outcomeBadge = {
    resolved: "bg-aegis-ok/20 text-aegis-ok",
    stabilized: "bg-aegis-warn/20 text-aegis-warn",
    escalated: "bg-aegis-danger/20 text-aegis-danger",
  }[item.outcome];
  const confidencePct =
    item.ai_confidence === null ? null : Math.round(item.ai_confidence * 100);
  return (
    <li>
      <Link
        to={`/incidents/${item.incident_id}`}
        className="grid grid-cols-1 items-baseline gap-2 px-5 py-3 hover:bg-aegis-bg/40 sm:grid-cols-[80px_1fr_auto_auto]"
      >
        <span className="font-mono text-[10px] text-aegis-muted">
          {new Date(item.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-aegis-text">{item.incident_title}</span>
          <span className="rounded border border-aegis-border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-aegis-muted">
            {item.action_category}
          </span>
        </div>
        <span className="font-mono text-[10px] text-aegis-muted">
          {confidencePct === null ? "" : `Confidence: ${confidencePct}%`}
        </span>
        <span
          className={`rounded px-2 py-0.5 text-center font-mono text-[10px] uppercase tracking-widest ${outcomeBadge}`}
        >
          {item.outcome}
        </span>
      </Link>
    </li>
  );
}

/* ─── Top Active Policies sidebar ────────────────────────────── */

function TopPoliciesPanel({
  policies,
}: {
  policies: { policy_id: string | null; name: string; actions_count: number }[];
}) {
  return (
    <aside className="rounded-lg border border-aegis-border bg-aegis-panel">
      <header className="flex items-baseline justify-between border-b border-aegis-border px-4 py-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Top Active Policies (24h)
        </h3>
        <Link
          to="/policies"
          className="font-mono text-[10px] text-aegis-accent hover:underline"
        >
          View all →
        </Link>
      </header>
      <ul className="divide-y divide-aegis-border">
        {policies.length === 0 && (
          <li className="p-4 text-sm text-aegis-muted">No policies seeded yet.</li>
        )}
        {policies.map((p) => (
          <li
            key={p.policy_id ?? p.name}
            className="flex items-baseline justify-between gap-3 px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-aegis-text">{p.name}</div>
              {p.policy_id && (
                <div className="font-mono text-[10px] text-aegis-muted">
                  {p.policy_id.slice(0, 8)}…
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold text-aegis-accent">
                {p.actions_count}
              </div>
              <div className="font-mono text-[9px] uppercase tracking-widest text-aegis-muted">
                Actions
              </div>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/* ─── Requires Your Attention ─────────────────────────────────── */

function RequiresAttentionRow({
  attention,
}: {
  attention: {
    critical_escalations: number;
    pending_reviews: number;
    stabilized_systems: number;
  };
}) {
  const cards = [
    {
      key: "critical",
      label: "Critical Escalations",
      value: attention.critical_escalations,
      note: "High risk issues require immediate attention",
      cta: { to: "/incidents?status=escalated", label: "Review now" },
      tone: "danger" as const,
    },
    {
      key: "pending",
      label: "Pending Reviews",
      value: attention.pending_reviews,
      note: "Actions awaiting your review",
      cta: { to: "/approvals", label: "Review queue" },
      tone: "warn" as const,
    },
    {
      key: "stabilized",
      label: "Stabilized Systems",
      value: attention.stabilized_systems,
      note: "Temporarily stabilized awaiting permanent fix",
      cta: { to: "/incidents", label: "View systems" },
      tone: "accent" as const,
    },
  ];
  return (
    <section>
      <header className="mb-3 flex items-baseline justify-between">
        <h2 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Requires Your Attention
        </h2>
      </header>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {cards.map((c) => {
          const toneClass = {
            danger: "text-aegis-danger",
            warn: "text-aegis-warn",
            accent: "text-aegis-accent",
          }[c.tone];
          return (
            <div
              key={c.key}
              className="flex flex-col gap-2 rounded-lg border border-aegis-border bg-aegis-panel p-4"
            >
              <div className={`font-mono text-xs uppercase tracking-widest ${toneClass}`}>
                {c.label}
              </div>
              <div className="text-3xl font-semibold text-aegis-text">{c.value}</div>
              <div className="text-xs text-aegis-muted">{c.note}</div>
              <Link
                to={c.cta.to}
                className={`mt-auto pt-1 font-mono text-[10px] uppercase tracking-widest ${toneClass} hover:underline`}
              >
                {c.cta.label} →
              </Link>
            </div>
          );
        })}
      </div>
    </section>
  );
}

