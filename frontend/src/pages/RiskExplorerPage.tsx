import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getRiskAnalytics, getRiskCategory, type RiskWindow } from "@/lib/risk";
import { TrendChart } from "@/components/risk/TrendChart";

/**
 * Sprint 12: Risk Explorer — per-category drill-down.
 *
 * Picks up where Risk Analytics leaves off. The Analytics page shows the
 * roll-up; this page lets an operator click into one category (Identity,
 * Endpoint, Network, …) and see the actions, contributing action classes,
 * and the trend scoped to that category alone.
 */

const WINDOWS: { value: RiskWindow; label: string }[] = [
  { value: "24h", label: "Last 24h" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

export default function RiskExplorerPage() {
  const [window, setWindow] = useState<RiskWindow>("7d");

  const { data: analytics } = useQuery({
    queryKey: ["risk-analytics", window],
    queryFn: () => getRiskAnalytics(window),
  });

  const categories = analytics?.categories ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  const activeCategory = selected ?? categories[0]?.name ?? null;

  const { data: drilldown, isLoading } = useQuery({
    queryKey: ["risk-category", activeCategory, window],
    queryFn: () => getRiskCategory(activeCategory as string, window),
    enabled: !!activeCategory,
  });

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-aegis-text">Risk Explorer</h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            Drill into one risk category at a time
          </p>
        </div>
        <nav className="flex overflow-hidden rounded border border-aegis-border font-mono text-xs">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              type="button"
              onClick={() => setWindow(w.value)}
              className={`px-3 py-1.5 ${
                window === w.value
                  ? "bg-aegis-accent text-aegis-bg"
                  : "text-aegis-muted hover:text-aegis-text"
              }`}
            >
              {w.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
        <aside className="rounded-lg border border-aegis-border bg-aegis-panel">
          <header className="border-b border-aegis-border px-4 py-3">
            <h3 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
              Categories
            </h3>
          </header>
          <ul>
            {categories.length === 0 && (
              <li className="p-4 text-sm text-aegis-muted">
                No category activity in this window.
              </li>
            )}
            {categories.map((c) => {
              const active = c.name === activeCategory;
              return (
                <li key={c.name}>
                  <button
                    type="button"
                    onClick={() => setSelected(c.name)}
                    className={`flex w-full items-baseline justify-between px-4 py-3 text-left ${
                      active
                        ? "bg-aegis-bg/60 text-aegis-text"
                        : "text-aegis-muted hover:bg-aegis-bg/30 hover:text-aegis-text"
                    }`}
                  >
                    <span className="text-sm">{c.name}</span>
                    <span className="font-mono text-xs">{c.current_actions}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <section>
          {!activeCategory && (
            <div className="rounded-lg border border-aegis-border bg-aegis-panel p-6 text-sm text-aegis-muted">
              Select a category on the left to drill in.
            </div>
          )}
          {activeCategory && (isLoading || !drilldown) && (
            <div className="rounded-lg border border-aegis-border bg-aegis-panel p-6 text-sm text-aegis-muted">
              Loading {activeCategory}…
            </div>
          )}
          {activeCategory && drilldown && (
            <CategoryDetail data={drilldown} />
          )}
        </section>
      </div>

      <p className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        <Link to="/risk-analytics" className="text-aegis-accent hover:underline">
          ← back to Risk Analytics
        </Link>
      </p>
    </div>
  );
}

/* ─── Category detail ────────────────────────────────────────── */

function CategoryDetail({
  data,
}: {
  data: {
    category: string;
    window: RiskWindow;
    summary: {
      actions_count: number;
      prior_count: number;
      delta_pct: number | null;
      est_risk_reduced: number;
    };
    trend: number[];
    recent_actions: {
      action_id: string;
      action_class: string;
      incident_id: string;
      incident_title: string;
      incident_severity: string;
      outcome: string;
      ai_confidence: number | null;
      created_at: string;
    }[];
    contributing_classes: { action_class: string; count: number }[];
  };
}) {
  const deltaTone =
    data.summary.delta_pct === null || data.summary.delta_pct === 0
      ? "text-aegis-muted"
      : data.summary.delta_pct < 0
        ? "text-aegis-ok"
        : "text-aegis-warn";
  return (
    <div className="space-y-4">
      <header className="rounded-lg border border-aegis-border bg-aegis-panel p-5">
        <div className="flex flex-wrap items-baseline gap-6">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
              Category
            </div>
            <div className="mt-1 text-2xl font-semibold text-aegis-text">
              {data.category}
            </div>
          </div>
          <Stat label="Actions" value={data.summary.actions_count} />
          <Stat label="Prior window" value={data.summary.prior_count} subdued />
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
              Change
            </div>
            <div className={`mt-1 text-lg font-semibold ${deltaTone}`}>
              {data.summary.delta_pct === null
                ? "—"
                : `${data.summary.delta_pct > 0 ? "↑" : "↓"} ${Math.abs(data.summary.delta_pct).toFixed(1)}%`}
            </div>
          </div>
          <Stat
            label="Risk reduced"
            value={data.summary.est_risk_reduced}
            tone="ok"
          />
        </div>
      </header>

      <section className="rounded-lg border border-aegis-border bg-aegis-panel p-5">
        <header className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-aegis-text">
            Actions in {data.category}
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            Bucketed activity over {data.window}
          </span>
        </header>
        <div className="text-aegis-accent">
          <TrendChart data={data.trend} label={`${data.category} actions`} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_240px]">
        <RecentActions rows={data.recent_actions} />
        <ContributingClasses rows={data.contributing_classes} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  subdued,
  tone,
}: {
  label: string;
  value: number;
  subdued?: boolean;
  tone?: "ok";
}) {
  const cls = tone === "ok" ? "text-aegis-ok" : "text-aegis-text";
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </div>
      <div
        className={`mt-1 text-lg font-semibold ${subdued ? "text-aegis-muted" : cls}`}
      >
        {value}
      </div>
    </div>
  );
}

function RecentActions({
  rows,
}: {
  rows: {
    action_id: string;
    action_class: string;
    incident_id: string;
    incident_title: string;
    incident_severity: string;
    outcome: string;
    ai_confidence: number | null;
    created_at: string;
  }[];
}) {
  const tones: Record<string, string> = {
    resolved: "bg-aegis-ok/15 text-aegis-ok",
    stabilized: "bg-aegis-warn/15 text-aegis-warn",
    escalated: "bg-aegis-danger/15 text-aegis-danger",
  };
  return (
    <section className="rounded-lg border border-aegis-border bg-aegis-panel">
      <header className="border-b border-aegis-border px-5 py-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Recent actions ({rows.length})
        </h3>
      </header>
      {rows.length === 0 ? (
        <p className="p-5 text-sm text-aegis-muted">
          No actions in this window for this category.
        </p>
      ) : (
        <ul className="divide-y divide-aegis-border">
          {rows.map((a) => (
            <li key={a.action_id}>
              <Link
                to={`/incidents/${a.incident_id}`}
                className="grid grid-cols-1 gap-1 px-5 py-3 hover:bg-aegis-bg/40 sm:grid-cols-[100px_1fr_auto]"
              >
                <span className="font-mono text-[10px] text-aegis-muted">
                  {new Date(a.created_at).toLocaleString()}
                </span>
                <div>
                  <span className="text-sm text-aegis-text">{a.incident_title}</span>
                  <div className="font-mono text-[10px] text-aegis-muted">
                    {a.action_class} ·{" "}
                    {a.ai_confidence === null
                      ? "confidence —"
                      : `confidence ${Math.round(a.ai_confidence * 100)}%`}
                  </div>
                </div>
                <span
                  className={`self-start rounded px-2 py-0.5 text-center font-mono text-[10px] uppercase tracking-widest ${tones[a.outcome] ?? ""}`}
                >
                  {a.outcome}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ContributingClasses({
  rows,
}: {
  rows: { action_class: string; count: number }[];
}) {
  return (
    <aside className="rounded-lg border border-aegis-border bg-aegis-panel">
      <header className="border-b border-aegis-border px-4 py-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Contributing classes
        </h3>
      </header>
      <ul className="divide-y divide-aegis-border">
        {rows.length === 0 ? (
          <li className="p-4 text-sm text-aegis-muted">No data.</li>
        ) : (
          rows.map((r) => (
            <li
              key={r.action_class}
              className="flex items-baseline justify-between px-4 py-2"
            >
              <span className="font-mono text-xs text-aegis-text">
                {r.action_class}
              </span>
              <span className="font-mono text-sm text-aegis-accent">{r.count}</span>
            </li>
          ))
        )}
      </ul>
    </aside>
  );
}
