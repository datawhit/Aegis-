import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "@/lib/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate("/incidents", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-8">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-aegis-border bg-aegis-panel p-8"
      >
        <header className="mb-6 flex items-baseline justify-between">
          <h1 className="font-mono text-xl">aegis</h1>
          <span className="text-xs uppercase tracking-widest text-aegis-muted">
            sign in
          </span>
        </header>

        <label className="block text-xs uppercase tracking-widest text-aegis-muted">
          email
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 block w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 font-mono text-sm text-aegis-text focus:border-aegis-accent focus:outline-none"
          />
        </label>

        <label className="block text-xs uppercase tracking-widest text-aegis-muted">
          password
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 block w-full rounded border border-aegis-border bg-aegis-bg px-3 py-2 font-mono text-sm text-aegis-text focus:border-aegis-accent focus:outline-none"
          />
        </label>

        {error && (
          <div className="text-xs text-aegis-danger">{error}</div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-aegis-accent py-2 font-mono text-sm text-aegis-bg disabled:opacity-50"
        >
          {submitting ? "signing in…" : "sign in"}
        </button>

        <p className="text-xs text-aegis-muted">
          Dev default: <code className="text-aegis-text">admin@aegis.local</code> /{" "}
          <code className="text-aegis-text">aegis-dev-admin</code>
        </p>
      </form>
    </div>
  );
}
