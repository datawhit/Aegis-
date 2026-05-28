import { useQuery } from "@tanstack/react-query";
import { listApprovals } from "@/lib/approvals";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";

export default function ApprovalInboxPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => listApprovals({ pendingOnly: true }),
    refetchInterval: 5_000,
  });

  return (
    <section>
      <header className="mb-6 flex items-baseline justify-between">
        <h2 className="font-mono text-sm uppercase tracking-widest text-aegis-muted">
          approval inbox
        </h2>
        {data && (
          <span className="font-mono text-xs text-aegis-muted">
            {data.length} pending
          </span>
        )}
      </header>

      {isLoading && (
        <p className="text-sm text-aegis-muted">loading…</p>
      )}
      {isError && (
        <p className="text-sm text-aegis-danger">
          error: {(error as Error).message}
        </p>
      )}
      {data && data.length === 0 && (
        <p className="text-sm text-aegis-muted">
          No pending approvals. Quiet shift.
        </p>
      )}
      <div className="space-y-3">
        {data?.map((item) => (
          <ApprovalCard key={item.approval.id} item={item} />
        ))}
      </div>
    </section>
  );
}
