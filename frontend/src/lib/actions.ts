import { api } from "@/lib/api";

export type ActionOutcome = "resolved" | "stabilized" | "escalated";

export type ActionFeedItem = {
  action_id: string;
  incident_id: string;
  incident_title: string;
  incident_severity: "info" | "low" | "medium" | "high" | "critical";
  action_class: string;
  action_category: string;
  outcome: ActionOutcome;
  ai_confidence: number | null;
  created_at: string;
  executed_at: string | null;
  policy_id: string | null;
};

export type ActionFeedResponse = {
  items: ActionFeedItem[];
  counts: Record<"all" | "resolved" | "stabilized" | "escalated", number>;
};

export async function listActionsFeed(
  opts: { status?: "all" | ActionOutcome; limit?: number } = {},
): Promise<ActionFeedResponse> {
  const { data } = await api.get<ActionFeedResponse>("/actions/feed", {
    params: { status: opts.status ?? "all", limit: opts.limit ?? 50 },
  });
  return data;
}
