import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listApprovals } from "@/lib/approvals";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";

export default function ApprovalInboxPage() {
  const [pendingOnly, setPendingOnly] = useState(true);
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["approvals", pendingOnly ? "pending" : "all"],
    queryFn: () => listApprovals({ pendingOnly }),
    refetchInterval: 5_000,
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    if (!q) return data;
    return data.filter(
      (item) =>
        item.incident_title.toLowerCase().includes(q) ||
        item.action_class.toLowerCase().includes(q) ||
        (item.ai_summary?.toLowerCase().includes(q) ?? false),
    );
  }, [data, search]);

  return (
    <section>
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-mono text-sm uppercase tracking-widest text-aegis-muted">
          approval inbox
        </h2>
        {data && (
          <span className="font-mono text-xs text-aegis-muted">
            {filtered.length} of {data.length} {pendingOnly ? "pending" : "total"}
          </span>
        )}
      </header>

      <div className="mb-4 flex flex-wrap gap-3 rounded border border-aegis-border bg-aegis-panel p-3">
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            scope
          </label>
          <div className="flex overflow-hidden rounded border border-aegis-border font-mono text-xs">
            <button
              type="button"
              onClick={() => setPendingOnly(true)}
              className={`px-3 py-1 ${
                pendingOnly
                  ? "bg-aegis-accent text-aegis-bg"
                  : "text-aegis-muted hover:text-aegis-text"
              }`}
            >
              pending
            </button>
            <button
              type="button"
              onClick={() => setPendingOnly(false)}
              className={`border-l border-aegis-border px-3 py-1 ${
                !pendingOnly
                  ? "bg-aegis-accent text-aegis-bg"
                  : "text-aegis-muted hover:text-aegis-text"
              }`}
            >
              all
            </button>
          </div>
        </div>

        <div className="flex flex-1 items-center gap-2">
          <label className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            search
          </label>
          <input
            type="search"
            placeholder="title, action, summary"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 rounded border border-aegis-border bg-aegis-bg px-2 py-1 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
          />
        </div>
      </div>

      {isLoading && <p className="text-sm text-aegis-muted">loading…</p>}
      {isError && (
        <p className="text-sm text-aegis-danger">
          error: {(error as Error).message}
        </p>
      )}
      {data && filtered.length === 0 && (
        <p className="text-sm text-aegis-muted">
          {data.length === 0
            ? pendingOnly
              ? "No pending approvals. Quiet shift."
              : "No approvals yet."
            : "No approvals match the current search."}
        </p>
      )}
      <div className="space-y-3">
        {filtered.map((item) => (
          <ApprovalCard key={item.approval.id} item={item} />
        ))}
      </div>
    </section>
  );
}
