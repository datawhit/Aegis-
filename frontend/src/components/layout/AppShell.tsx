import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { logout } from "@/lib/auth";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-center justify-between border-b border-aegis-border bg-aegis-panel px-6 py-3">
        <Link to="/incidents" className="font-mono text-sm tracking-widest">
          aegis
        </Link>
        <nav className="flex items-center gap-6 text-xs text-aegis-muted">
          <Link to="/incidents" className="hover:text-aegis-text">
            incidents
          </Link>
          <span className="text-aegis-muted">
            {user?.email} · {user?.role}
          </span>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="text-aegis-muted hover:text-aegis-danger"
          >
            sign out
          </button>
        </nav>
      </header>
      <main className="flex-1 bg-aegis-bg p-6">
        <Outlet />
      </main>
    </div>
  );
}
