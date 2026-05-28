import { useState } from "react";
import type { AIReasoningRead } from "@/lib/incidents";

/**
 * Surfaces the AI's reasoning for an incident. The product principle this
 * UI enforces: an analyst should be able to *read why* the AI proposed
 * what it proposed before approving or rejecting it.
 */
export function AIReasoningPanel({ snapshots }: { snapshots: AIReasoningRead[] }) {
  if (snapshots.length === 0) {
    return (
      <div className="rounded border border-aegis-border bg-aegis-bg p-4 text-sm text-aegis-muted">
        No AI reasoning captured yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {snapshots.map((s) => (
        <ReasoningCard key={s.id} snapshot={s} />
      ))}
    </div>
  );
}

function ReasoningCard({ snapshot: s }: { snapshot: AIReasoningRead }) {
  const [showPrompt, setShowPrompt] = useState(false);
  return (
    <article className="rounded border border-aegis-border bg-aegis-bg p-4 text-sm">
      <header className="mb-3 flex flex-wrap items-baseline gap-3 text-xs text-aegis-muted">
        <span className="font-mono">{s.provider}/{s.model}</span>
        <span>{s.prompt_template_id ?? "no template"}</span>
        <span>
          confidence{" "}
          {s.confidence === null
            ? "—"
            : `${Math.round(s.confidence * 100)}%`}
        </span>
        <span>{new Date(s.created_at).toLocaleString()}</span>
        {s.latency_ms !== null && <span>{s.latency_ms} ms</span>}
        {s.prompt_tokens !== null && (
          <span>
            {s.prompt_tokens}p / {s.completion_tokens}c tokens
          </span>
        )}
      </header>

      <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-1 font-mono text-xs">
        {s.structured_output.severity && (
          <>
            <dt className="text-aegis-muted">severity</dt>
            <dd className="text-aegis-text">{s.structured_output.severity}</dd>
          </>
        )}
        {s.structured_output.category && (
          <>
            <dt className="text-aegis-muted">category</dt>
            <dd className="text-aegis-text">{s.structured_output.category}</dd>
          </>
        )}
        {!!s.structured_output.mitre_techniques?.length && (
          <>
            <dt className="text-aegis-muted">MITRE</dt>
            <dd className="text-aegis-text">
              {s.structured_output.mitre_techniques.join(", ")}
            </dd>
          </>
        )}
        {s.structured_output.suggested_action_class && (
          <>
            <dt className="text-aegis-muted">suggested</dt>
            <dd className="text-aegis-accent">
              {s.structured_output.suggested_action_class}
            </dd>
          </>
        )}
      </dl>

      {s.structured_output.reasoning && (
        <p className="mt-3 whitespace-pre-wrap text-sm text-aegis-text">
          {s.structured_output.reasoning}
        </p>
      )}

      {s.prompt && (
        <details
          className="mt-3 cursor-pointer text-xs text-aegis-muted"
          open={showPrompt}
          onToggle={(e) => setShowPrompt((e.target as HTMLDetailsElement).open)}
        >
          <summary className="select-none hover:text-aegis-text">
            show prompt sent to model (PII redacted)
          </summary>
          <pre className="mt-2 max-h-96 overflow-auto rounded border border-aegis-border bg-aegis-panel p-3 text-[11px] text-aegis-text">
            {s.prompt}
          </pre>
        </details>
      )}
    </article>
  );
}
