import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api";

/**
 * Phase 0 App is intentionally trivial — it exists to prove the wiring
 * (Vite → React → React Query → axios → FastAPI). Sprint 1 replaces this
 * with the real routing tree and dashboard.
 */
export default function App() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5000,
  });

  return (
    <main className="flex min-h-full items-center justify-center p-8">
      <div className="w-full max-w-xl rounded-2xl border border-aegis-border bg-aegis-panel p-8 shadow-2xl">
        <header className="mb-6 flex items-baseline justify-between">
          <h1 className="font-mono text-xl text-aegis-text">aegis</h1>
          <span className="text-xs uppercase tracking-widest text-aegis-muted">
            phase 0 — foundation
          </span>
        </header>

        <p className="mb-6 text-sm text-aegis-muted">
          AI-governed Autonomous Security Operations Governance Platform.
          This view proves the local dev wiring: the call below hits{" "}
          <code className="font-mono text-aegis-accent">
            GET /api/v1/health
          </code>{" "}
          every 5s.
        </p>

        <section className="rounded-lg border border-aegis-border bg-aegis-bg p-4 font-mono text-sm">
          {isLoading && <span className="text-aegis-muted">checking…</span>}
          {isError && (
            <span className="text-aegis-danger">
              error: {(error as Error)?.message ?? "unknown"}
            </span>
          )}
          {data && (
            <div className="space-y-1">
              <div>
                <span className="text-aegis-muted">status:</span>{" "}
                <span className="text-aegis-ok">{data.status}</span>
              </div>
              <div>
                <span className="text-aegis-muted">version:</span>{" "}
                <span className="text-aegis-text">{data.version}</span>
              </div>
            </div>
          )}
        </section>

        <footer className="mt-6 text-xs text-aegis-muted">
          Sprint 1: alert ingestion + AI triage. See docs/CHANGELOG.md.
        </footer>
      </div>
    </main>
  );
}
