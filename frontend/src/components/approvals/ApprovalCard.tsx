import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { decideApproval, type ApprovalListItem } from "@/lib/approvals";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";

export function ApprovalCard({ item }: { item: ApprovalListItem }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");

  const mutation = useMutation({
    mutationFn: (approve: boolean) =>
      decideApproval(item.approval.id, approve, note || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["incident", item.incident_id] });
    },
  });

  const confidence =
    item.ai_confidence === null
      ? "—"
      : `${Math.round(item.ai_confidence * 100)}%`;

  return (
    <article className="rounded border border-aegis-border bg-aegis-panel p-4">
      <header className="mb-3 flex flex-wrap items-baseline gap-3">
        <SeverityBadge severity={item.incident_severity} />
        <Link
          to={`/incidents/${item.incident_id}`}
          className="text-sm text-aegis-text hover:underline"
        >
          {item.incident_title}
        </Link>
        <span className="ml-auto font-mono text-[10px] text-aegis-muted">
          expires {new Date(item.approval.expires_at).toLocaleString()}
        </span>
      </header>

      <dl className="mb-3 grid grid-cols-[120px_1fr] gap-x-4 gap-y-1 font-mono text-xs">
        <dt className="text-aegis-muted">action</dt>
        <dd className="text-aegis-accent">{item.action_class}</dd>
        <dt className="text-aegis-muted">blast radius</dt>
        <dd className="text-aegis-text">{item.blast_radius}</dd>
        <dt className="text-aegis-muted">ai confidence</dt>
        <dd className="text-aegis-text">{confidence}</dd>
        <dt className="text-aegis-muted">required role</dt>
        <dd className="text-aegis-text">{item.approval.requested_role}</dd>
      </dl>

      {item.ai_summary && (
        <p className="mb-3 text-sm text-aegis-text">{item.ai_summary}</p>
      )}

      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Optional decision note (audited)"
        className="mb-3 block w-full rounded border border-aegis-border bg-aegis-bg p-2 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
        rows={2}
      />

      <div className="flex gap-2">
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate(true)}
          className="rounded bg-aegis-ok px-3 py-1.5 font-mono text-xs text-aegis-bg disabled:opacity-50"
        >
          approve
        </button>
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate(false)}
          className="rounded bg-aegis-danger px-3 py-1.5 font-mono text-xs text-aegis-bg disabled:opacity-50"
        >
          reject
        </button>
        {mutation.isError && (
          <span className="ml-2 text-xs text-aegis-danger">
            {(mutation.error as Error).message}
          </span>
        )}
      </div>
    </article>
  );
}
