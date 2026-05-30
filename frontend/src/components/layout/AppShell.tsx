import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { logout } from "@/lib/auth";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex flex-col gap-3 border-b border-aegis-border bg-aegis-panel px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center justify-between">
          <Link to="/incidents" className="font-mono text-sm tracking-widest">
            aegis
          </Link>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="font-mono text-xs text-aegis-muted hover:text-aegis-danger sm:hidden"
          >
            sign out
          </button>
        </div>
        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-aegis-muted">
          <Link to="/incidents" className="hover:text-aegis-text">
            incidents
          </Link>
          <Link to="/approvals" className="hover:text-aegis-text">
            approvals
          </Link>
          <Link to="/policies" className="hover:text-aegis-text">
            policies
          </Link>
          <Link to="/audit-logs" className="hover:text-aegis-text">
            audit
          </Link>
          <span className="ml-auto truncate text-aegis-muted sm:ml-0">
            {user?.email} · {user?.role}
          </span>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="hidden text-aegis-muted hover:text-aegis-danger sm:inline"
          >
            sign out
          </button>
        </nav>
      </header>
      <main className="flex-1 bg-aegis-bg p-4 sm:p-6">
        <Outlet />
      </main>
    </div>
  );
}
