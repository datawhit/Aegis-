import { api } from "@/lib/api";

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type IncidentSummary = {
  id: string;
  title: string;
  severity: Severity;
  status: string;
  ai_confidence: number | null;
  mitre_techniques: string[];
  created_at: string;
  updated_at: string;
};

export type AlertRead = {
  id: string;
  source: string;
  source_event_id: string;
  correlation_key: string | null;
  severity: Severity;
  status: string;
  incident_id: string | null;
  created_at: string;
  normalized: Record<string, unknown>;
};

export type AIReasoningRead = {
  id: string;
  created_at: string;
  provider: string;
  model: string;
  prompt_template_id: string | null;
  structured_output: {
    severity?: Severity;
    category?: string;
    mitre_techniques?: string[];
    summary?: string;
    suggested_action_class?: string | null;
    confidence?: number;
    reasoning?: string;
  };
  confidence: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
};

export type RemediationActionRead = {
  id: string;
  action_class: string;
  status: string;
  parameters: Record<string, unknown>;
  rollback_plan: Record<string, unknown> | null;
  blast_radius: number;
  ai_confidence: number | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type IncidentDetail = IncidentSummary & {
  summary: string | null;
  affected_entities: Record<string, unknown>;
  alerts: AlertRead[];
  remediation_actions: RemediationActionRead[];
  reasoning_snapshots: AIReasoningRead[];
};

export type IncidentListResponse = {
  items: IncidentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export async function listIncidents(params: {
  status?: string;
  severity?: Severity;
  limit?: number;
  offset?: number;
} = {}): Promise<IncidentListResponse> {
  const { data } = await api.get<IncidentListResponse>("/incidents", {
    params,
  });
  return data;
}

export async function getIncident(id: string): Promise<IncidentDetail> {
  const { data } = await api.get<IncidentDetail>(`/incidents/${id}`);
  return data;
}
