import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useAlertSocket } from "../realtime/useAlertSocket";
import { SeverityBadge } from "./RiskBadge";

const ADMIN_LINKS = [
  { to: "/analytics", label: "Analytics" },
  { to: "/activity", label: "Browser time" },
  { to: "/interactions", label: "Interactions" },
  { to: "/alerts", label: "Alerts" },
  { to: "/shadow", label: "Shadow AI" },
  { to: "/policies", label: "Policies" },
  { to: "/users", label: "Users" },
  { to: "/audit", label: "Audit log" },
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

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";
  const { connected, latest, dismiss } = useAlertSocket(isAdmin);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">🛡️</span>
          <div>
            <strong>AI Usage Monitor</strong>
            <div className="brand-sub">DLP · consented capture</div>
          </div>
        </div>

        <nav>
          {!isAdmin && <NavLink to="/me">My activity</NavLink>}
          {!isAdmin && <NavLink to="/time">My time</NavLink>}
          {!isAdmin && <NavLink to="/digest">Weekly digest</NavLink>}
          {isAdmin && ADMIN_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to}>
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="who">
            <strong>{user?.full_name}</strong>
            <div className="muted">{user?.email}</div>
            <span className="role-chip">{user?.role}</span>
          </div>
          <button
            className="ghost"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <MonitoringIndicator
            consented={!!user?.consent_accepted}
            enrolled={!!user?.is_enrolled}
          />
          {isAdmin && (
            <span className={`live-pill ${connected ? "on" : ""}`}>
              {connected ? "● live alerts" : "○ live alerts reconnecting…"}
            </span>
          )}
          {!user?.consent_accepted && (
            <span className="hint">
              Enable capture from the extension popup to record activity
            </span>
          )}
        </header>

        <main className="page">
          <Outlet />
        </main>
      </div>

      {isAdmin && latest.length > 0 && (
        <div className="toasts">
          {latest.slice(0, 3).map((alert) => (
            <div key={alert.id} className={`toast toast-${alert.severity}`}>
              <div className="toast-head">
                <SeverityBadge severity={alert.severity} />
                <strong>{alert.title}</strong>
                <button className="x" onClick={() => dismiss(alert.id)} aria-label="Dismiss">
                  ×
                </button>
              </div>
              <p>{alert.summary}</p>
              <span className="muted">{new Date(alert.created_at).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
