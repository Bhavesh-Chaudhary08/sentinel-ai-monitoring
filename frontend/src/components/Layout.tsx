import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import BrandMark from "./BrandMark";

/* Minimal line icons, 16px grid, inheriting currentColor. */
const ICONS: Record<string, ReactNode> = {
  analytics: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path d="M4 19V5M4 19h16" strokeLinecap="round" />
      <path d="M8 15v-4M12 15V8M16 15v-6" strokeLinecap="round" />
    </svg>
  ),
  activity: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 8v4.4l2.8 1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  interactions: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path d="M4 6.5h16M4 12h16M4 17.5h10" strokeLinecap="round" />
    </svg>
  ),
  shadow: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path d="M2.8 12S6.1 6.2 12 6.2 21.2 12 21.2 12 17.9 17.8 12 17.8 2.8 12 2.8 12Z" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="2.6" />
    </svg>
  ),
  users: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <circle cx="9.5" cy="8.6" r="3.1" />
      <path d="M3.8 19c.5-3 2.9-4.7 5.7-4.7s5.2 1.7 5.7 4.7" strokeLinecap="round" />
      <path d="M16.4 6.1a3 3 0 0 1 0 5.6M18.2 18.9c-.2-1.7-.8-3-1.9-3.9" strokeLinecap="round" />
    </svg>
  ),
  me: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <circle cx="12" cy="8.4" r="3.4" />
      <path d="M5 19.4c.6-3.3 3.4-5.1 7-5.1s6.4 1.8 7 5.1" strokeLinecap="round" />
    </svg>
  ),
  time: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path d="M12 21a8.6 8.6 0 1 0 0-17.2A8.6 8.6 0 0 0 12 21Z" />
      <path d="M12 7.6V12l3 1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  digest: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <rect x="4" y="5.4" width="16" height="14" rx="2.4" />
      <path d="M4 10h16M9 3.8v3M15 3.8v3" strokeLinecap="round" />
    </svg>
  ),
};

const ADMIN_LINKS = [
  { to: "/analytics", label: "Analytics", icon: "analytics" },
  { to: "/activity", label: "Browser time", icon: "activity" },
  { to: "/interactions", label: "Interactions", icon: "interactions" },
  { to: "/shadow", label: "Shadow AI", icon: "shadow" },
  { to: "/users", label: "Users", icon: "users" },
];

const EMPLOYEE_LINKS = [
  { to: "/me", label: "My activity", icon: "me" },
  { to: "/time", label: "My time", icon: "time" },
  { to: "/digest", label: "Weekly digest", icon: "digest" },
];

/**
 * Persistent, always-visible monitoring indicator (feature #7): employees see
 * their capture state on every dashboard screen, not just in a settings page.
 */
function MonitoringIndicator({ consented, enrolled }: { consented: boolean; enrolled: boolean }) {
  const active = consented && enrolled;
  return (
    <span className={`monitor-pill ${active ? "on" : "off"}`} title="Extension capture state">
      <span className="dot" />
      {active ? "Monitoring ON" : "Monitoring off"}
    </span>
  );
}

function initials(name?: string) {
  if (!name) return "··";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isAdmin = user?.role === "admin";
  const links = isAdmin ? ADMIN_LINKS : EMPLOYEE_LINKS;
  const current = links.find((link) => location.pathname.startsWith(link.to));

  return (
    <div className="shell">
      <div className="app-glow" aria-hidden="true" />

      <aside className="sidebar">
        <div className="brand">
          <span className="brand-logo">
            <BrandMark />
          </span>
          <div className="brand-text">
            <strong>Sentinel</strong>
            <span className="brand-sub">AI usage · DLP</span>
          </div>
        </div>

        <nav>
          <div className="nav-section">{isAdmin ? "Admin console" : "My workspace"}</div>
          {links.map((link) => (
            <NavLink key={link.to} to={link.to}>
              <span className="nav-icon">{ICONS[link.icon]}</span>
              <span>{link.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="who">
            <span className="avatar">{initials(user?.full_name)}</span>
            <div style={{ minWidth: 0 }}>
              <strong>{user?.full_name}</strong>
              <div className="muted">{user?.email}</div>
            </div>
          </div>
          <div className="footer-row">
            <span className="role-chip">{user?.role}</span>
            <button
              className="ghost small"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <div className="crumbs">
            <span className="prod">sentinel</span>
            <span className="sep">/</span>
            <strong>{current?.label ?? "Dashboard"}</strong>
          </div>
          <div className="topbar-right">
            {!user?.consent_accepted && (
              <span className="hint">Enable capture from the extension popup</span>
            )}
            <MonitoringIndicator
              consented={!!user?.consent_accepted}
              enrolled={!!user?.is_enrolled}
            />
          </div>
        </header>

        <main className="page">
          <div className="page-enter" key={location.pathname}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
