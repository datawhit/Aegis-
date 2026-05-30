import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import { logout } from "@/lib/auth";
import { listApprovals } from "@/lib/approvals";

/**
 * Sprint 9: operator-first AppShell.
 *
 * Left rail, grouped by pillars:
 *   - OPERATIONS:      Aegis Actions, Review Queue
 *   - GOVERNANCE:      Policies, Approvals, Audit Trail, Integrations
 *   - RISK INTEL.:     Risk Analytics, Risk Explorer (Sprint 11)
 *   - SETTINGS:        Settings, System Status
 *
 * "Overview" sits at the top, unsectioned — the default landing page.
 * Sub-pages keep their nav entry but are demoted from the top bar that
 * Sprints 1–8 used.
 */

type NavItem = {
  to: string;
  label: string;
  icon: string;
  badge?: number;
  comingSoon?: boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

function useReviewQueueBadge(): number | undefined {
  const { data } = useQuery({
    queryKey: ["approvals", "pending", "shell"],
    queryFn: () => listApprovals({ pendingOnly: true }),
    refetchInterval: 30_000,
  });
  return data?.length;
}

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const pendingCount = useReviewQueueBadge();

  const groups: NavGroup[] = [
    {
      label: "Operations",
      items: [
        { to: "/incidents", label: "Aegis Actions", icon: "•" },
        {
          to: "/approvals",
          label: "Review Queue",
          icon: "•",
          badge: pendingCount,
        },
      ],
    },
    {
      label: "Governance",
      items: [
        { to: "/policies", label: "Policies", icon: "•" },
        { to: "/audit-logs", label: "Audit Trail", icon: "•" },
      ],
    },
    {
      label: "Risk Intelligence",
      items: [
        { to: "/risk-analytics", label: "Risk Analytics", icon: "•" },
        { to: "/risk-explorer", label: "Risk Explorer", icon: "•" },
      ],
    },
    {
      label: "Settings",
      items: [{ to: "/settings", label: "System Status", icon: "•", comingSoon: true }],
    },
  ];

  return (
    <div className="flex min-h-full">
      {/* ───── Sidebar ───── */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-aegis-border bg-aegis-panel lg:flex">
        <Link
          to="/overview"
          className="flex flex-col px-5 pb-4 pt-5 hover:bg-aegis-bg/30"
        >
          <span className="font-mono text-sm font-semibold tracking-widest">
            AEGIS
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            Autonomous SOC
          </span>
        </Link>

        <NavLink
          to="/overview"
          className={({ isActive }) =>
            `mx-3 mb-4 flex items-center gap-2 rounded px-3 py-2 font-mono text-xs tracking-widest ${
              isActive
                ? "bg-aegis-accent/10 text-aegis-accent"
                : "text-aegis-muted hover:text-aegis-text"
            }`
          }
        >
          Overview
        </NavLink>

        {groups.map((group) => (
          <div key={group.label} className="mb-4 px-3">
            <div className="px-3 pb-2 font-mono text-[10px] uppercase tracking-[0.15em] text-aegis-muted/70">
              {group.label}
            </div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center justify-between rounded px-3 py-1.5 font-mono text-xs ${
                    isActive
                      ? "bg-aegis-bg/50 text-aegis-text"
                      : "text-aegis-muted hover:text-aegis-text"
                  } ${item.comingSoon ? "opacity-50" : ""}`
                }
                onClick={(e) => {
                  if (item.comingSoon) e.preventDefault();
                }}
              >
                <span>{item.label}</span>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="rounded bg-aegis-danger/20 px-1.5 py-0.5 font-mono text-[10px] text-aegis-danger">
                    {item.badge}
                  </span>
                )}
                {item.comingSoon && (
                  <span className="font-mono text-[9px] uppercase text-aegis-muted">
                    soon
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        ))}

        <div className="mt-auto border-t border-aegis-border px-5 py-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-aegis-bg font-mono text-xs text-aegis-accent">
              {(user?.display_name || user?.email || "?").slice(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 overflow-hidden">
              <div className="truncate font-mono text-xs text-aegis-text">
                {user?.display_name || user?.email}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
                {user?.role}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted hover:text-aegis-danger"
          >
            sign out
          </button>
        </div>

        <div className="border-t border-aegis-border px-5 py-3">
          <div className="font-mono text-[10px] uppercase tracking-widest text-aegis-muted">
            System Status
          </div>
          <div className="mt-1 flex items-center gap-2 font-mono text-xs text-aegis-ok">
            <span className="h-1.5 w-1.5 rounded-full bg-aegis-ok" />
            All systems operational
          </div>
        </div>
      </aside>

      {/* ───── Mobile/condensed top bar (sidebar is hidden below lg) ───── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-aegis-border bg-aegis-panel px-4 py-3 lg:hidden">
          <Link to="/overview" className="font-mono text-sm tracking-widest">
            AEGIS
          </Link>
          <nav className="flex items-center gap-4 font-mono text-xs text-aegis-muted">
            <Link to="/overview" className="hover:text-aegis-text">overview</Link>
            <Link to="/incidents" className="hover:text-aegis-text">actions</Link>
            <Link to="/approvals" className="hover:text-aegis-text">review</Link>
            <button
              type="button"
              onClick={() => {
                logout();
                navigate("/login", { replace: true });
              }}
              className="hover:text-aegis-danger"
            >
              sign out
            </button>
          </nav>
        </header>
        <main className="flex-1 bg-aegis-bg p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
