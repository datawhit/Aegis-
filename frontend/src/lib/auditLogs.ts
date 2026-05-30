import { api } from "@/lib/api";

export type AuditLogEntry = {
  id: string;
  created_at: string;
  actor_type: "user" | "system" | "ai" | "integration" | "service";
  actor_id: string | null;
  actor_label: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  payload: Record<string, unknown>;
  reasoning_snapshot_id: string | null;
  prev_hash: string | null;
  entry_hash: string;
};

export type AuditLogPage = {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
};

export type AuditLogFilters = {
  limit?: number;
  offset?: number;
  actor_type?: string;
  action?: string;
  resource_type?: string;
};

export async function listAuditLogs(
  filters: AuditLogFilters = {},
): Promise<AuditLogPage> {
  const { data } = await api.get<AuditLogPage>("/audit/logs", {
    params: {
      limit: filters.limit ?? 50,
      offset: filters.offset ?? 0,
      actor_type: filters.actor_type || undefined,
      action: filters.action || undefined,
      resource_type: filters.resource_type || undefined,
    },
  });
  return data;
}

export async function exportSignedAudit(since?: string): Promise<Blob> {
  const { data } = await api.get<Blob>("/audit/export", {
    params: { since: since || undefined },
    responseType: "blob",
  });
  return data;
}
