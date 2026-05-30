import { api } from "@/lib/api";

export type PolicyEffect = "allow" | "escalate" | "deny";

export type PolicyRead = {
  id: string;
  name: string;
  description: string | null;
  priority: number;
  effect: PolicyEffect;
  match: Record<string, unknown>;
  constraints: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type PolicyWrite = {
  name: string;
  description?: string | null;
  priority: number;
  effect: PolicyEffect;
  match: Record<string, unknown>;
  constraints: Record<string, unknown>;
  is_active: boolean;
};

export async function listPolicies(): Promise<PolicyRead[]> {
  const { data } = await api.get<{ items: PolicyRead[] }>("/policies");
  return data.items;
}

export async function getPolicy(id: string): Promise<PolicyRead> {
  const { data } = await api.get<PolicyRead>(`/policies/${id}`);
  return data;
}

export async function createPolicy(body: PolicyWrite): Promise<PolicyRead> {
  const { data } = await api.post<PolicyRead>("/policies", body);
  return data;
}

export async function updatePolicy(
  id: string,
  body: Partial<PolicyWrite>,
): Promise<PolicyRead> {
  const { data } = await api.put<PolicyRead>(`/policies/${id}`, body);
  return data;
}

export async function deletePolicy(id: string): Promise<void> {
  await api.delete(`/policies/${id}`);
}
