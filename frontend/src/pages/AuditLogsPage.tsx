import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  exportSignedAudit,
  listAuditLogs,
  type AuditLogEntry,
  type AuditLogFilters,
} from "@/lib/auditLogs";

const PAGE_SIZE = 50;

const ACTOR_TYPES = ["", "user", "system", "ai", "integration", "service"];

const actorColor: Record<string, string> = {
  user: "text-aegis-accent",
  system: "text-aegis-muted",
  ai: "text-aegis-warn",
  integration: "text-aegis-text",
  service: "text-aegis-muted",
};

export default function AuditLogsPage() {
  // Sprint 13 (D-72): seed filters from URL query params so deep links
  // from the Decision Record's Audit Trail tab pre-filter the view.
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<AuditLogFilters>(() => ({
    limit: PAGE_SIZE,
    offset: 0,
    actor_type: searchParams.get("actor_type") || undefined,
    action: searchParams.get("action") || undefined,
    resource_type: searchParams.get("resource_type") || undefined,
    resource_id: searchParams.get("resource_id") || undefined,
  }));
  const [selected, setSelected] = useState<AuditLogEntry | null>(null);

  // Keep URL in sync with filters so back/refresh round-trips work.
  useEffect(() => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries({
      actor_type: filters.actor_type,
      action: filters.action,
      resource_type: filters.resource_type,
      resource_id: filters.resource_id,
    })) {
      if (v) next.set(k, v);
    }
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.actor_type, filters.action, filters.resource_type, filters.resource_id]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["auditLogs", filters],
    queryFn: () => listAuditLogs(filters),
  });

  const setFilter = (patch: Partial<AuditLogFilters>) =>
    setFilters((f) => ({ ...f, offset: 0, ...patch }));

  const downloadExport = async () => {
    const blob = await exportSignedAudit();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audits_export_${new Date().toISOString().slice(0, 10)}.ndjson`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <section>
      <header className="mb-6 flex items-baseline justify-between">
        <h2 className="font-mono text-sm uppercase tracking-widest text-aegis-muted">
          audit chain explorer
        </h2>
        <div className="flex items-center gap-4">
          {data && (
            <span className="font-mono text-xs text-aegis-muted">
              {data.total} entries
            </span>
          )}
          <button
            type="button"
            onClick={downloadExport}
            className="rounded border border-aegis-accent px-3 py-1 font-mono text-xs text-aegis-accent hover:bg-aegis-accent hover:text-aegis-bg"
          >
            download signed export
          </button>
        </div>
      </header>

      {filters.resource_id && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded border border-aegis-accent/40 bg-aegis-accent/5 px-3 py-2 font-mono text-xs text-aegis-accent">
          <span>scoped to {filters.resource_type ?? "resource"}</span>
          <code className="text-aegis-text">{filters.resource_id.slice(0, 8)}…</code>
          <button
            type="button"
            onClick={() => setFilter({ resource_id: undefined, resource_type: undefined })}
            className="ml-auto text-aegis-muted hover:text-aegis-danger"
          >
            clear filter
          </button>
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-3 rounded border border-aegis-border bg-aegis-panel p-3">
        <FilterField label="actor type">
          <select
            value={filters.actor_type ?? ""}
            onChange={(e) => setFilter({ actor_type: e.target.value || undefined })}
            className="rounded border border-aegis-border bg-aegis-bg px-2 py-1 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
          >
            {ACTOR_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || "(any)"}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="action">
          <input
            type="text"
            placeholder="incident.created"
            value={filters.action ?? ""}
            onChange={(e) => setFilter({ action: e.target.value || undefined })}
            className="w-48 rounded border border-aegis-border bg-aegis-bg px-2 py-1 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
          />
        </FilterField>
        <FilterField label="resource type">
          <input
            type="text"
            placeholder="incident"
            value={filters.resource_type ?? ""}
            onChange={(e) =>
              setFilter({ resource_type: e.target.value || undefined })
            }
            className="w-32 rounded border border-aegis-border bg-aegis-bg px-2 py-1 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
          />
        </FilterField>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_400px]">
        <div className="rounded-lg border border-aegis-border bg-aegis-panel">
          {isLoading && (
            <div className="p-6 text-sm text-aegis-muted">loading…</div>
          )}
          {isError && (
            <div className="p-6 text-sm text-aegis-danger">
              error: {(error as Error).message}
            </div>
          )}
          {data && data.items.length === 0 && (
            <div className="p-6 text-sm text-aegis-muted">
              No audit entries match the current filters.
            </div>
          )}
          {data?.items.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => setSelected(entry)}
              className={`flex w-full flex-col gap-1 border-b border-aegis-border px-4 py-2 text-left last:border-b-0 hover:bg-aegis-bg/40 sm:grid sm:grid-cols-[80px_1fr_auto] sm:items-baseline sm:gap-3 ${
                selected?.id === entry.id ? "bg-aegis-bg/60" : ""
              }`}
            >
              <div className="flex items-baseline gap-3 sm:contents">
                <span
                  className={`font-mono text-[10px] uppercase ${actorColor[entry.actor_type] ?? ""}`}
                >
                  {entry.actor_type}
                </span>
                <span className="break-all font-mono text-xs text-aegis-text">
                  {entry.action}
                </span>
              </div>
              <span className="font-mono text-[10px] text-aegis-muted sm:text-right">
                {new Date(entry.created_at).toLocaleString()}
              </span>
            </button>
          ))}

          {data && data.total > (filters.limit ?? PAGE_SIZE) && (
            <div className="flex items-center justify-between border-t border-aegis-border p-3 font-mono text-xs text-aegis-muted">
              <button
                type="button"
                disabled={(filters.offset ?? 0) === 0}
                onClick={() =>
                  setFilters((f) => ({
                    ...f,
                    offset: Math.max(0, (f.offset ?? 0) - (f.limit ?? PAGE_SIZE)),
                  }))
                }
                className="hover:text-aegis-text disabled:opacity-30"
              >
                ← prev
              </button>
              <span>
                {(filters.offset ?? 0) + 1}–
                {Math.min(
                  (filters.offset ?? 0) + (filters.limit ?? PAGE_SIZE),
                  data.total,
                )}{" "}
                / {data.total}
              </span>
              <button
                type="button"
                disabled={
                  (filters.offset ?? 0) + (filters.limit ?? PAGE_SIZE) >= data.total
                }
                onClick={() =>
                  setFilters((f) => ({
                    ...f,
                    offset: (f.offset ?? 0) + (f.limit ?? PAGE_SIZE),
                  }))
                }
                className="hover:text-aegis-text disabled:opacity-30"
              >
                next →
              </button>
            </div>
          )}
        </div>

        <aside className="rounded-lg border border-aegis-border bg-aegis-panel p-4 text-xs">
          {selected ? <EntryDetail entry={selected} /> : (
            <p className="text-aegis-muted">Select an entry to inspect.</p>
          )}
        </aside>
      </div>
    </section>
  );
}

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </label>
      {children}
    </div>
  );
}

function EntryDetail({ entry }: { entry: AuditLogEntry }) {
  return (
    <div className="space-y-3 font-mono">
      <Row label="action" value={entry.action} />
      <Row label="actor" value={`${entry.actor_type}${entry.actor_label ? ` (${entry.actor_label})` : ""}`} />
      <Row label="resource" value={`${entry.resource_type}${entry.resource_id ? ` ${entry.resource_id.slice(0, 8)}…` : ""}`} />
      <Row label="when" value={new Date(entry.created_at).toLocaleString()} />
      <Row
        label="entry hash"
        value={<span className="break-all text-aegis-accent">{entry.entry_hash.slice(0, 32)}…</span>}
      />
      <Row
        label="prev hash"
        value={
          entry.prev_hash ? (
            <span className="break-all text-aegis-muted">
              {entry.prev_hash.slice(0, 32)}…
            </span>
          ) : (
            <span className="text-aegis-warn">(genesis)</span>
          )
        }
      />
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-widest text-aegis-muted">
          payload
        </div>
        <pre className="max-h-64 overflow-auto rounded border border-aegis-border bg-aegis-bg p-2 text-[10px] text-aegis-text">
          {JSON.stringify(entry.payload, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-2">
      <span className="text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </span>
      <span className="text-aegis-text">{value}</span>
    </div>
  );
}
