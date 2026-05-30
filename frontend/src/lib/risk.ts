import { api } from "@/lib/api";

export type RiskWindow = "24h" | "7d" | "30d";

export type RiskSummary = {
  window: RiskWindow;
  current_score: number;
  prior_score: number;
  delta_pct: number | null;
  label: "Low" | "Medium" | "High" | "Critical";
};

export type RiskHistoryPoint = { t: string; score: number };

export type RiskCategoryRow = {
  name: string;
  current_actions: number;
  prior_actions: number;
  delta_pct: number | null;
  trend: number[];
};

export type TopReducingPolicy = {
  policy_id: string;
  name: string;
  actions_count: number;
  est_risk_reduced: number;
};

export type RiskAnalyticsResponse = {
  generated_at: string;
  summary: RiskSummary;
  score_history: RiskHistoryPoint[];
  categories: RiskCategoryRow[];
  top_reducing: TopReducingPolicy[];
};

export async function getRiskAnalytics(
  window: RiskWindow = "7d",
): Promise<RiskAnalyticsResponse> {
  const { data } = await api.get<RiskAnalyticsResponse>("/risk/analytics", {
    params: { window },
  });
  return data;
}

// ── Sprint 12: per-category drill-down ──────────────────────────────

export type CategoryActionRow = {
  action_id: string;
  action_class: string;
  incident_id: string;
  incident_title: string;
  incident_severity: "info" | "low" | "medium" | "high" | "critical";
  outcome: "resolved" | "stabilized" | "escalated";
  ai_confidence: number | null;
  created_at: string;
};

export type CategoryDrilldownResponse = {
  category: string;
  window: RiskWindow;
  summary: {
    actions_count: number;
    prior_count: number;
    delta_pct: number | null;
    est_risk_reduced: number;
  };
  trend: number[];
  recent_actions: CategoryActionRow[];
  contributing_classes: { action_class: string; count: number }[];
};

export async function getRiskCategory(
  category: string,
  window: RiskWindow = "7d",
): Promise<CategoryDrilldownResponse> {
  const { data } = await api.get<CategoryDrilldownResponse>(
    `/risk/category/${encodeURIComponent(category)}`,
    { params: { window } },
  );
  return data;
}
