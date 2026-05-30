import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  chatWithAssistant,
  type AssistantChatResponse,
  type AssistantSource,
} from "@/lib/assistant";

/**
 * Sprint 10: Aegis Assistant chat panel.
 *
 * Stateless on the server today — each turn is a fresh request. Local
 * client state holds the conversation so the operator sees the prior
 * exchange.
 */

type Turn =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string;
      sources: AssistantSource[];
      toolCalls: string[];
    }
  | { role: "error"; text: string };

const SUGGESTED_QUERIES = [
  "What did you do overnight?",
  "Why did you revoke this session?",
  "Which policies generated the most actions?",
  "How much risk did we reduce this week?",
];

export function AegisAssistantPanel() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const mutation = useMutation({
    mutationFn: (q: string) => chatWithAssistant(q),
    onSuccess: (data: AssistantChatResponse) => {
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: data.answer,
          sources: data.sources,
          toolCalls: data.tool_calls,
        },
      ]);
    },
    onError: (err: Error) => {
      setTurns((t) => [
        ...t,
        {
          role: "error",
          text:
            err.message ||
            "Assistant request failed. Check that AEGIS_ANTHROPIC_API_KEY is configured.",
        },
      ]);
    },
  });

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [turns, mutation.isPending]);

  const send = (q: string) => {
    if (!q.trim() || mutation.isPending) return;
    setTurns((t) => [...t, { role: "user", text: q }]);
    setDraft("");
    mutation.mutate(q);
  };

  return (
    <section className="rounded-lg border border-aegis-accent/30 bg-aegis-panel p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-aegis-text">Aegis Assistant</h2>
        <span className="rounded border border-aegis-accent/40 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-widest text-aegis-accent">
          beta
        </span>
      </header>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        Ask Aegis anything about your security operations
      </p>

      {turns.length === 0 && !mutation.isPending && (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED_QUERIES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => send(q)}
              className="rounded border border-aegis-border bg-aegis-bg px-3 py-1.5 font-mono text-[11px] text-aegis-muted hover:border-aegis-accent hover:text-aegis-text"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {turns.length > 0 && (
        <div
          ref={transcriptRef}
          className="mt-3 max-h-72 space-y-3 overflow-y-auto rounded border border-aegis-border bg-aegis-bg p-3 text-sm"
        >
          {turns.map((turn, idx) => (
            <TurnView key={idx} turn={turn} />
          ))}
          {mutation.isPending && (
            <div className="font-mono text-xs text-aegis-muted">Aegis is thinking…</div>
          )}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          type="text"
          placeholder="Ask Aegis…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={mutation.isPending}
          className="flex-1 rounded border border-aegis-border bg-aegis-bg px-3 py-2 text-sm text-aegis-text focus:border-aegis-accent focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!draft.trim() || mutation.isPending}
          className="rounded bg-aegis-accent px-3 py-2 font-mono text-xs text-aegis-bg disabled:opacity-50"
        >
          send
        </button>
      </form>
    </section>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="text-right">
        <span className="inline-block rounded bg-aegis-accent/15 px-3 py-1.5 text-sm text-aegis-text">
          {turn.text}
        </span>
      </div>
    );
  }
  if (turn.role === "error") {
    return (
      <div className="rounded border border-aegis-danger/30 bg-aegis-danger/5 px-3 py-2 text-sm text-aegis-danger">
        {turn.text}
      </div>
    );
  }
  return (
    <div>
      <p className="whitespace-pre-wrap text-sm text-aegis-text">{turn.text}</p>
      {turn.sources.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2">
          {turn.sources.map((s) => (
            <li key={`${s.kind}:${s.id}`}>
              <SourceLink source={s} />
            </li>
          ))}
        </ul>
      )}
      {turn.toolCalls.length > 0 && (
        <div className="mt-2 font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
          Tools used: {turn.toolCalls.join(", ")}
        </div>
      )}
    </div>
  );
}

function SourceLink({ source }: { source: AssistantSource }) {
  const href = {
    incident: `/incidents/${source.id}`,
    action: `/incidents/${source.id}`, // actions surface inside their incident
    policy: `/policies/${source.id}`,
  }[source.kind];
  const tone = {
    incident: "border-aegis-warn/40 text-aegis-warn",
    action: "border-aegis-accent/40 text-aegis-accent",
    policy: "border-aegis-ok/40 text-aegis-ok",
  }[source.kind];
  return (
    <Link
      to={href}
      className={`inline-block rounded border bg-aegis-bg px-2 py-0.5 font-mono text-[10px] ${tone} hover:underline`}
      title={`${source.kind}: ${source.id}`}
    >
      {source.kind}: {truncate(source.label, 28)}
    </Link>
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}
