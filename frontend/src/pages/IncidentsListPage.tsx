import { useQuery } from "@tanstack/react-query";
import { listIncidents } from "@/lib/incidents";
import { IncidentRow } from "@/components/incidents/IncidentRow";

export default function IncidentsListPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => listIncidents({ limit: 100 }),
    refetchInterval: 10_000,
  });

  return (
    <section>
      <header className="mb-6 flex items-baseline justify-between">
        <h2 className="font-mono text-sm uppercase tracking-widest text-aegis-muted">
          incidents
        </h2>
        {data && (
          <span className="font-mono text-xs text-aegis-muted">
            {data.total} total
          </span>
        )}
      </header>

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
            No incidents yet. Send a signed POST to{" "}
            <code className="text-aegis-text">/api/v1/ingest/defender</code> to
            generate one.
          </div>
        )}
        {data?.items.map((incident) => (
          <IncidentRow key={incident.id} incident={incident} />
        ))}
      </div>
    </section>
  );
}
