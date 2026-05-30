import { api } from "@/lib/api";

export type AssistantSource = {
  kind: "incident" | "action" | "policy";
  id: string;
  label: string;
};

export type AssistantChatResponse = {
  answer: string;
  sources: AssistantSource[];
  tool_calls: string[];
  model: string;
};

export async function chatWithAssistant(
  message: string,
): Promise<AssistantChatResponse> {
  const { data } = await api.post<AssistantChatResponse>("/assistant/chat", {
    message,
  });
  return data;
}
