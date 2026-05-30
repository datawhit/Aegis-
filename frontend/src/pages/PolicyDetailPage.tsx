import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import {
  createPolicy,
  deletePolicy,
  getPolicy,
  type PolicyEffect,
  type PolicyWrite,
  updatePolicy,
} from "@/lib/policies";

const EMPTY: PolicyWrite = {
  name: "",
  description: "",
  priority: 100,
  effect: "escalate",
  match: { any: true },
  constraints: { requires_approval: true },
  is_active: true,
};

export default function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === "new";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const role = useAuthStore((s) => s.user?.role);
  const isAdmin = role === "admin";

  const { data, isLoading } = useQuery({
    queryKey: ["policy", id],
    queryFn: () => getPolicy(id!),
    enabled: !isNew,
  });

  const [form, setForm] = useState<PolicyWrite>(EMPTY);
  const [matchText, setMatchText] = useState(JSON.stringify(EMPTY.match, null, 2));
  const [constraintsText, setConstraintsText] = useState(
    JSON.stringify(EMPTY.constraints, null, 2),
  );
  const [jsonError, setJsonError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setForm({
        name: data.name,
        description: data.description,
        priority: data.priority,
        effect: data.effect,
        match: data.match,
        constraints: data.constraints,
        is_active: data.is_active,
      });
      setMatchText(JSON.stringify(data.match, null, 2));
      setConstraintsText(JSON.stringify(data.constraints, null, 2));
    }
  }, [data]);

  const save = useMutation({
    mutationFn: async () => {
      let match: Record<string, unknown>;
      let constraints: Record<string, unknown>;
      try {
        match = JSON.parse(matchText);
        constraints = JSON.parse(constraintsText);
      } catch (err) {
        setJsonError((err as Error).message);
        throw err;
      }
      setJsonError(null);
      const body: PolicyWrite = { ...form, match, constraints };
      return isNew ? createPolicy(body) : updatePolicy(id!, body);
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["policies"] });
      queryClient.invalidateQueries({ queryKey: ["policy", saved.id] });
      navigate(`/policies/${saved.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: () => deletePolicy(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policies"] });
      navigate("/policies");
    },
  });

  if (!isNew && isLoading) {
    return <div className="text-sm text-aegis-muted">loading…</div>;
  }

  return (
    <section className="mx-auto max-w-3xl">
      <header className="mb-6 flex items-baseline justify-between">
        <h2 className="font-mono text-sm uppercase tracking-widest text-aegis-muted">
          {isNew ? "new policy" : "edit policy"}
        </h2>
        <Link
          to="/policies"
          className="font-mono text-xs text-aegis-muted hover:text-aegis-text"
        >
          ← back to list
        </Link>
      </header>

      {!isAdmin && (
        <div className="mb-4 rounded border border-aegis-warn bg-aegis-panel p-3 text-xs text-aegis-warn">
          You are viewing this policy in read-only mode. Editing requires the
          admin role.
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (isAdmin) save.mutate();
        }}
        className="space-y-4 rounded-lg border border-aegis-border bg-aegis-panel p-6"
      >
        <Field label="name">
          <input
            type="text"
            disabled={!isAdmin}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 text-sm text-aegis-text focus:border-aegis-accent focus:outline-none"
            required
          />
        </Field>

        <Field label="description">
          <textarea
            disabled={!isAdmin}
            value={form.description || ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 text-sm text-aegis-text focus:border-aegis-accent focus:outline-none"
            rows={2}
          />
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="priority">
            <input
              type="number"
              disabled={!isAdmin}
              value={form.priority}
              onChange={(e) =>
                setForm({ ...form, priority: parseInt(e.target.value, 10) || 0 })
              }
              className="w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 text-sm text-aegis-text focus:border-aegis-accent focus:outline-none"
            />
          </Field>
          <Field label="effect">
            <select
              disabled={!isAdmin}
              value={form.effect}
              onChange={(e) =>
                setForm({ ...form, effect: e.target.value as PolicyEffect })
              }
              className="w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 text-sm text-aegis-text focus:border-aegis-accent focus:outline-none"
            >
              <option value="allow">allow</option>
              <option value="escalate">escalate</option>
              <option value="deny">deny</option>
            </select>
          </Field>
          <Field label="active">
            <label className="flex items-center gap-2 pt-2 text-sm text-aegis-text">
              <input
                type="checkbox"
                disabled={!isAdmin}
                checked={form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
              />
              enabled
            </label>
          </Field>
        </div>

        <Field label="match (JSON DSL)">
          <textarea
            disabled={!isAdmin}
            value={matchText}
            onChange={(e) => setMatchText(e.target.value)}
            className="w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
            rows={6}
            spellCheck={false}
          />
        </Field>

        <Field label="constraints (JSON)">
          <textarea
            disabled={!isAdmin}
            value={constraintsText}
            onChange={(e) => setConstraintsText(e.target.value)}
            className="w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 font-mono text-xs text-aegis-text focus:border-aegis-accent focus:outline-none"
            rows={4}
            spellCheck={false}
          />
        </Field>

        {jsonError && (
          <p className="text-xs text-aegis-danger">JSON parse error: {jsonError}</p>
        )}
        {save.isError && (
          <p className="text-xs text-aegis-danger">
            {(save.error as Error).message}
          </p>
        )}

        {isAdmin && (
          <div className="flex items-center justify-between pt-2">
            <button
              type="submit"
              disabled={save.isPending}
              className="rounded bg-aegis-accent px-4 py-2 font-mono text-xs text-aegis-bg disabled:opacity-50"
            >
              {save.isPending ? "saving…" : isNew ? "create" : "save"}
            </button>
            {!isNew && (
              <button
                type="button"
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`Delete policy "${form.name}"?`)) {
                    remove.mutate();
                  }
                }}
                className="rounded border border-aegis-danger px-4 py-2 font-mono text-xs text-aegis-danger hover:bg-aegis-danger hover:text-aegis-bg disabled:opacity-50"
              >
                delete
              </button>
            )}
          </div>
        )}
      </form>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
        {label}
      </label>
      {children}
    </div>
  );
}
