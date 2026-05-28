import { api } from "@/lib/api";

export type ApprovalRead = {
  id: string;
  remediation_action_id: string;
  state: "pending" | "approved" | "rejected" | "expired";
  requested_role: string;
  expires_at: string;
  decided_by_user_id: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
};

export type ApprovalListItem = {
  approval: ApprovalRead;
  incident_id: string;
  incident_title: string;
  incident_severity: "info" | "low" | "medium" | "high" | "critical";
  action_class: string;
  blast_radius: number;
  ai_confidence: number | null;
  ai_summary: string | null;
};

export async function listApprovals(opts: { pendingOnly?: boolean } = {}) {
  const { data } = await api.get<{ items: ApprovalListItem[] }>("/approvals", {
    params: { pending_only: opts.pendingOnly ?? true },
  });
  return data.items;
}

export async function decideApproval(
  id: string,
  approve: boolean,
  note?: string,
): Promise<ApprovalRead> {
  const { data } = await api.post<ApprovalRead>(`/approvals/${id}/decision`, {
    approve,
    note,
  });
  return data;
}

export async function rollbackRemediation(
  remediationActionId: string,
  reason: string,
): Promise<{ ok: boolean; new_status: string; error: string | null; dry_run: boolean }> {
  const { data } = await api.post(`/remediations/${remediationActionId}/rollback`, {
    reason,
  });
  return data;
}
