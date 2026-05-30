import { api } from "@/lib/api";

export type OvernightSummary = {
  issues_evaluated: number;
  resolved_autonomously: number;
  stabilized: number;
  escalated: number;
  analyst_hours_saved: number;
  mean_response_time_seconds: number | null;
  deltas: Record<string, number>;
};

export type TrustScore = {
  score: number;
  label: "Excellent" | "Good" | "Fair" | "Poor";
  rollbacks_24h: number;
  policy_adherence_pct_7d: number;
  rollback_rate_pct_30d: number;
};

export type RiskSnapshot = {
  score: number;
  label: "Low" | "Medium" | "High" | "Critical";
  delta_pct: number | null;
};

export type RequiresAttention = {
  critical_escalations: number;
  pending_reviews: number;
  stabilized_systems: number;
};

export type TopPolicy = {
  policy_id: string | null;
  name: string;
  actions_count: number;
};

export type OverviewResponse = {
  generated_at: string;
  overnight_summary: OvernightSummary;
  trust_score: TrustScore;
  risk_snapshot: RiskSnapshot;
  requires_attention: RequiresAttention;
  top_policies_24h: TopPolicy[];
};

export async function getOverview(): Promise<OverviewResponse> {
  const { data } = await api.get<OverviewResponse>("/overview");
  return data;
}
