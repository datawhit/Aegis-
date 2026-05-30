import { api } from "@/lib/api";

export type AssistantSource = {
  kind: "incident" | "action" | "policy";
  id: string;
  label: string;
};

export type AssistantChatResponse = {
  conversation_id: string;
  answer: string;
  sources: AssistantSource[];
  tool_calls: string[];
  model: string;
};

export async function chatWithAssistant(
  message: string,
  conversationId?: string,
): Promise<AssistantChatResponse> {
  const { data } = await api.post<AssistantChatResponse>("/assistant/chat", {
    message,
    conversation_id: conversationId ?? null,
  });
  return data;
}

// ── Sprint 13: server-side conversation history ─────────────────────

export type ConversationListItem = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type TranscriptMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: AssistantSource[];
  tool_calls: string[];
  model: string | null;
  created_at: string;
};

export type TranscriptResponse = {
  conversation_id: string;
  title: string | null;
  messages: TranscriptMessage[];
};

export async function listConversations(): Promise<ConversationListItem[]> {
  const { data } = await api.get<{ items: ConversationListItem[] }>(
    "/assistant/conversations",
  );
  return data.items;
}

export async function getTranscript(
  conversationId: string,
): Promise<TranscriptResponse> {
  const { data } = await api.get<TranscriptResponse>(
    `/assistant/conversations/${conversationId}`,
  );
  return data;
}
