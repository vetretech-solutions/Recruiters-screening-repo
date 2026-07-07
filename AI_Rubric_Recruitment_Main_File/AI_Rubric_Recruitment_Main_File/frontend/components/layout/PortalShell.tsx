"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { portalApi, PortalUser } from "@/lib/portal-api";
import { canAccessTab, defaultRouteForRole, NAV_CONFIG, navItemsForRole, SIDEBAR_EXCLUDED_KEYS, WORKSPACE_NAV_KEYS } from "@/lib/portal-nav";
import { clearSession, getStoredToken, getStoredUser, saveSession } from "@/lib/session";
import "@/app/portal.css";

export default function PortalShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<PortalUser | null>(null);
  const [ready, setReady] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(true);

  useEffect(() => {
    const stored = getStoredUser();
    if (!stored) {
      router.replace("/login");
      setReady(true);
      return;
    }

    setUser(stored);
    setReady(true);

    let cancelled = false;

    portalApi
      .me()
      .then((fresh) => {
        if (cancelled) return;
        const token = getStoredToken();
        if (token) saveSession(token, fresh);
        setUser(fresh);
      })
      .catch(() => {
        if (cancelled) return;
        clearSession();
        router.replace("/login");
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!user) return;
    const segment = pathname.split("/")[1] || "";
    if (segment && !canAccessTab(user.role, segment)) {
      router.replace(defaultRouteForRole(user.role));
    }
  }, [pathname, router, user]);

  useEffect(() => {
    if (!user) return;
    const workspaceKeys = new Set<string>(WORKSPACE_NAV_KEYS);
    const items = navItemsForRole(user.role).filter((item) => workspaceKeys.has(item));
    const active = items.some((item) => {
      const href = NAV_CONFIG[item].href;
      return pathname === href || pathname.startsWith(`${href}/`);
    });
    if (active) setWorkspaceOpen(true);
  }, [pathname, user]);

  if (!ready || !user) {
    return (
      <div className="portal-shell portal-shell--loading">
        <main className="portal-content">Loading...</main>
      </div>
    );
  }

  const navItems = navItemsForRole(user.role);
  const firstName = user.full_name.split(" ")[0];
  const isScreening = pathname.startsWith("/screening");

  const sidebarExcluded = new Set<string>(SIDEBAR_EXCLUDED_KEYS);
  const workspaceKeys = new Set<string>(WORKSPACE_NAV_KEYS);
  const workspaceItems = navItems.filter((item) => workspaceKeys.has(item));
  const otherNavItems = navItems.filter((item) => !workspaceKeys.has(item) && !sidebarExcluded.has(item));
  const workspaceActive = workspaceItems.some((item) => {
    const href = NAV_CONFIG[item].href;
    return pathname === href || pathname.startsWith(`${href}/`);
  });

  return (
    <div className="portal-shell">
      <div className="portal-brand-bar">
        <div className="portal-brand">
          <div className="navbar-logo">AR</div>
          <div>
            <h1>AI Recruiter Portal</h1>
          </div>
        </div>
      </div>

      <header className="portal-header">
        <div className="navbar-actions">
          <span className="portal-greeting">Hello, {firstName}</span>
          <div className="user-pill">
            <div className="user-avatar">
              {(user.full_name?.charAt(0) || user.email.charAt(0)).toUpperCase()}
            </div>
            <span className="user-pill-name">{user.full_name}</span>
            <span className="user-pill-role">· {user.role.replace("_", " ")}</span>
          </div>
          <button
            className="btn btn-portal-logout"
            type="button"
            title="Logout"
            onClick={() => {
              clearSession();
              router.push("/");
            }}
          >
            Logout
          </button>
        </div>
      </header>

      <aside className="portal-sidebar">
        <nav className="portal-sidebar-nav">
          {otherNavItems.map((item) => {
            const cfg = NAV_CONFIG[item];
            const label = cfg.label;
            const active = pathname === cfg.href || pathname.startsWith(cfg.href + "/");
            return (
              <Link
                key={item}
                href={cfg.href}
                className={`portal-sidebar-link${active ? " active" : ""}`}
              >
                {label}
              </Link>
            );
          })}

          {workspaceItems.length > 0 && (
            <div className="portal-sidebar-group">
              <button
                type="button"
                className={`portal-sidebar-group-toggle${workspaceActive ? " active" : ""}`}
                aria-expanded={workspaceOpen}
                onClick={() => setWorkspaceOpen((open) => !open)}
              >
                <span>Hiring</span>
                <svg
                  className={`portal-sidebar-chevron${workspaceOpen ? " open" : ""}`}
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  aria-hidden="true"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              {workspaceOpen && (
                <div className="portal-sidebar-submenu">
                  {workspaceItems.map((item) => {
                    const cfg = NAV_CONFIG[item];
                    const active = pathname === cfg.href || pathname.startsWith(cfg.href + "/");
                    return (
                      <Link
                        key={item}
                        href={cfg.href}
                        className={`portal-sidebar-sublink${active ? " active" : ""}`}
                      >
                        {cfg.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </nav>
      </aside>

      <main className={`portal-content${isScreening ? " portal-content--screening" : ""}`}>
        {children}
      </main>
    </div>
  );
}
