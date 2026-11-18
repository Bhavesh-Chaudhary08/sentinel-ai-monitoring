import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const ADMIN_LINKS = [
  { to: "/analytics", label: "Analytics" },
  { to: "/activity", label: "Browser time" },
  { to: "/interactions", label: "Interactions" },
  { to: "/shadow", label: "Shadow AI" },
  { to: "/policies", label: "Policies" },
  { to: "/users", label: "Users" },
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
    </div>
  );
}
