import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import { listPolicies, type PolicyEffect } from "@/lib/policies";

const effectColor: Record<PolicyEffect, string> = {
  allow: "text-aegis-ok",
  escalate: "text-aegis-warn",
  deny: "text-aegis-danger",
};

export default function PoliciesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const isAdmin = role === "admin";

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["policies"],
    queryFn: listPolicies,
  });

  return (
    <section>
      <header className="mb-6 flex items-baseline justify-between">
        <h2 className="font-mono text-sm uppercase tracking-widest text-aegis-muted">
          policies
        </h2>
        <div className="flex items-center gap-4">
          {data && (
            <span className="font-mono text-xs text-aegis-muted">
              {data.length} total
            </span>
          )}
          {isAdmin && (
            <Link
              to="/policies/new"
              className="rounded border border-aegis-accent px-3 py-1 font-mono text-xs text-aegis-accent hover:bg-aegis-accent hover:text-aegis-bg"
            >
              + new policy
            </Link>
          )}
        </div>
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
        {data && data.length === 0 && (
          <div className="p-6 text-sm text-aegis-muted">
            No policies. The baseline-deny rule has not been seeded; run{" "}
            <code className="text-aegis-text">make seed-policies</code>.
          </div>
        )}
        {data?.map((p) => (
          <Link
            key={p.id}
            to={`/policies/${p.id}`}
            className="flex flex-col gap-1 border-b border-aegis-border px-4 py-3 last:border-b-0 hover:bg-aegis-bg/40 sm:grid sm:grid-cols-[60px_100px_1fr_120px_80px] sm:items-center sm:gap-4"
          >
            <div className="flex items-center gap-3 sm:contents">
              <span className="font-mono text-xs text-aegis-muted">
                #{p.priority}
              </span>
              <span
                className={`font-mono text-xs uppercase tracking-widest ${effectColor[p.effect]}`}
              >
                {p.effect}
              </span>
            </div>
            <span className="text-sm text-aegis-text">{p.name}</span>
            <div className="flex items-center justify-between sm:contents">
              <span className="font-mono text-[10px] text-aegis-muted">
                {p.is_active ? "active" : "disabled"}
              </span>
              <span className="font-mono text-[10px] text-aegis-muted sm:text-right">
                {new Date(p.updated_at).toLocaleDateString()}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
