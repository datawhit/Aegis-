import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getRiskAnalytics, type RiskWindow } from "@/lib/risk";
import { TrendChart } from "@/components/risk/TrendChart";

/**
 * Sprint 11: Risk Analytics page (Pillar 3 from ADR-022's reframe).
 *
 * Shows what risk Aegis is reducing — the differentiating story vs.
 * incident-queue products. Three sections:
 *   1. Header summary: current vs prior score, label, % delta.
 *   2. Score trend chart (inline SVG, no chart lib).
 *   3. Side-by-side: risk categories table + top reducing policies.
 *
 * Window selector (24h / 7d / 30d) drives both the trend and the
 * per-category deltas.
 */
const WINDOWS: { value: RiskWindow; label: string }[] = [
  { value: "24h", label: "Last 24h" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

export default function RiskAnalyticsPage() {
  const [window, setWindow] = useState<RiskWindow>("7d");
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["risk-analytics", window],
    queryFn: () => getRiskAnalytics(window),
    refetchInterval: 60_000,
  });

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-aegis-text">Risk Analytics</h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            What organisational risk Aegis is reducing, and how
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

      {isLoading && (
        <div className="rounded border border-aegis-border bg-aegis-panel p-6 text-sm text-aegis-muted">
          Loading risk analytics…
        </div>
      )}
      {isError && (
        <div className="rounded border border-aegis-border bg-aegis-panel p-6 text-sm text-aegis-danger">
          error: {(error as Error).message}
        </div>
      )}

      {data && (
        <>
          <SummaryCard
            label={data.summary.label}
            current={data.summary.current_score}
            prior={data.summary.prior_score}
            deltaPct={data.summary.delta_pct}
          />

          <section className="rounded-lg border border-aegis-border bg-aegis-panel p-5">
            <header className="mb-3 flex items-baseline justify-between">
              <h2 className="text-base font-semibold text-aegis-text">Risk Trend</h2>
              <span className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
                Score sampled every {bucketLabel(window)}; lower is better
              </span>
            </header>
            <div className={trendToneClass(data.summary.label)}>
              <TrendChart
                data={data.score_history.map((p) => p.score)}
                yMin={0}
                yMax={Math.max(50, ...data.score_history.map((p) => p.score))}
                label="Risk score trend"
              />
            </div>
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_360px]">
            <CategoriesPanel rows={data.categories} window={window} />
            <TopReducingPanel rows={data.top_reducing} />
          </div>

          <p className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            Generated at {new Date(data.generated_at).toLocaleString()} ·{" "}
            <Link to="/overview" className="text-aegis-accent hover:underline">
              ← back to Overview
            </Link>
          </p>
        </>
      )}
    </div>
  );
}

/* ─── Summary card ─────────────────────────────────────────────── */

function SummaryCard({
  label,
  current,
  prior,
  deltaPct,
}: {
  label: "Low" | "Medium" | "High" | "Critical";
  current: number;
  prior: number;
  deltaPct: number | null;
}) {
  const tone = riskToneClass(label);
  return (
    <section className="rounded-lg border border-aegis-border bg-aegis-panel p-5">
      <div className="flex flex-wrap items-baseline gap-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            Current Risk Score
          </div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className={`text-5xl font-semibold ${tone}`}>{current}</span>
            <span className="font-mono text-xs text-aegis-muted">/100</span>
            <span
              className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${tone} bg-current/10`}
            >
              {label}
            </span>
          </div>
        </div>
        <Arrow />
        <Delta label="Previous window" value={prior.toString()} subdued />
        <Delta
          label="Change"
          value={
            deltaPct === null
              ? "—"
              : `${deltaPct > 0 ? "↑" : "↓"} ${Math.abs(deltaPct).toFixed(1)}%`
          }
          tone={
            deltaPct === null
              ? "neutral"
              : deltaPct < 0
                ? "ok"
                : deltaPct === 0
                  ? "neutral"
                  : "danger"
          }
        />
        <p className="ml-auto max-w-md text-sm text-aegis-muted">
          Risk score is a 0-100 scalar; lower is better. Calculated from open
          incidents weighted by severity. Calibration to customer-specific
          baselines lands in a future sprint (D-52).
        </p>
      </div>
    </section>
  );
}

function Arrow() {
  return <span className="font-mono text-2xl text-aegis-muted">→</span>;
}

function Delta({
  label,
  value,
  tone = "neutral",
  subdued,
}: {
  label: string;
  value: string;
  tone?: "ok" | "danger" | "neutral";
  subdued?: boolean;
}) {
  const cls =
    tone === "ok"
      ? "text-aegis-ok"
      : tone === "danger"
        ? "text-aegis-danger"
        : "text-aegis-text";
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </div>
      <div
        className={`mt-1 text-2xl font-semibold ${subdued ? "text-aegis-muted" : cls}`}
      >
        {value}
      </div>
    </div>
  );
}

/* ─── Categories ──────────────────────────────────────────────── */

function CategoriesPanel({
  rows,
  window,
}: {
  rows: {
    name: string;
    current_actions: number;
    prior_actions: number;
    delta_pct: number | null;
    trend: number[];
  }[];
  window: RiskWindow;
}) {
  return (
    <section className="rounded-lg border border-aegis-border bg-aegis-panel">
      <header className="flex items-baseline justify-between border-b border-aegis-border px-5 py-4">
        <h2 className="text-base font-semibold text-aegis-text">
          Risk Categories
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
          Actions taken in {humanWindow(window)} by category
        </span>
      </header>
      {rows.length === 0 && (
        <p className="p-5 text-sm text-aegis-muted">
          No Aegis actions in this window. Categories appear here as activity
          accumulates.
        </p>
      )}
      <ul className="divide-y divide-aegis-border">
        {rows.map((r) => {
          const tone =
            r.delta_pct === null || r.delta_pct === 0
              ? "text-aegis-muted"
              : r.delta_pct > 0
                ? "text-aegis-warn"
                : "text-aegis-ok";
          return (
            <li
              key={r.name}
              className="grid grid-cols-1 items-baseline gap-3 px-5 py-3 sm:grid-cols-[140px_1fr_80px_auto]"
            >
              <div className="text-sm text-aegis-text">{r.name}</div>
              <div className="text-aegis-accent">
                <TrendChart
                  data={r.trend}
                  variant="sparkline"
                  height={28}
                  paddingX={0}
                  paddingY={2}
                />
              </div>
              <div className="font-mono text-xs text-aegis-text">
                {r.current_actions} <span className="text-aegis-muted">actions</span>
              </div>
              <div className={`text-right font-mono text-xs ${tone}`}>
                {r.delta_pct === null
                  ? "—"
                  : `${r.delta_pct > 0 ? "↑" : "↓"} ${Math.abs(r.delta_pct).toFixed(1)}%`}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ─── Top reducing policies ───────────────────────────────────── */

function TopReducingPanel({
  rows,
}: {
  rows: {
    policy_id: string;
    name: string;
    actions_count: number;
    est_risk_reduced: number;
  }[];
}) {
  return (
    <aside className="rounded-lg border border-aegis-border bg-aegis-panel">
      <header className="flex items-baseline justify-between border-b border-aegis-border px-4 py-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-aegis-muted">
          Top Reducing Policies
        </h3>
        <Link
          to="/policies"
          className="font-mono text-[10px] text-aegis-accent hover:underline"
        >
          All policies →
        </Link>
      </header>
      <ul className="divide-y divide-aegis-border">
        {rows.length === 0 && (
          <li className="p-4 text-sm text-aegis-muted">
            No policy-evaluated audit entries in this window yet.
          </li>
        )}
        {rows.map((p) => (
          <li
            key={p.policy_id}
            className="flex items-baseline justify-between gap-3 px-4 py-3"
          >
            <div className="min-w-0">
              <Link
                to={`/policies/${p.policy_id}`}
                className="block truncate text-sm text-aegis-text hover:text-aegis-accent"
              >
                {p.name}
              </Link>
              <div className="font-mono text-[10px] text-aegis-muted">
                {p.actions_count} actions · ~{p.est_risk_reduced} risk units
              </div>
            </div>
            <div className="font-mono text-sm font-semibold text-aegis-ok">
              -{p.est_risk_reduced}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/* ─── helpers ────────────────────────────────────────────────── */

function riskToneClass(label: "Low" | "Medium" | "High" | "Critical"): string {
  if (label === "Low") return "text-aegis-ok";
  if (label === "Medium") return "text-aegis-warn";
  return "text-aegis-danger";
}

function trendToneClass(label: "Low" | "Medium" | "High" | "Critical"): string {
  if (label === "Low") return "text-aegis-ok";
  if (label === "Medium") return "text-aegis-warn";
  return "text-aegis-danger";
}

function bucketLabel(w: RiskWindow): string {
  return { "24h": "2h", "7d": "12h", "30d": "1 day" }[w];
}

function humanWindow(w: RiskWindow): string {
  return { "24h": "the last 24 hours", "7d": "the last 7 days", "30d": "the last 30 days" }[w];
}
