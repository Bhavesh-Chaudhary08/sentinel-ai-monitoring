import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type Page, type User, type UserRole } from "../../api/client";

export default function Users() {
  const [data, setData] = useState<Page<User> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "employee" as UserRole,
    department: "",
    job_title: "",
  });

  const load = useCallback(async () => {
    try {
      setData(await api.users(1, 100));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const createUser = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createUser({
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role: form.role,
        department: form.department || undefined,
        job_title: form.job_title || undefined,
      });
      setShowForm(false);
      setForm({ email: "", full_name: "", password: "", role: "employee", department: "", job_title: "" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleStatus = async (user: User) => {
    try {
      await api.setUserStatus(user.id, !user.is_active);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <>
      <h1>Users &amp; enrollment</h1>
      <p className="page-sub">
        Accounts, roles, and consent state. Capture only ever runs for users who are
        <strong> enrolled + consented</strong> — everyone else is rejected at the API gate.
      </p>

      <div className="card">
        <div className="modal-head">
          <h2>Accounts ({data?.total ?? "…"})</h2>
          <button className="primary small" onClick={() => setShowForm((s) => !s)}>
            {showForm ? "Close" : "+ New user"}
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {showForm && (
          <form onSubmit={createUser} style={{ background: "var(--panel-2)", padding: 14, borderRadius: 12, marginTop: 12 }}>
            <div className="form-grid">
              <div>
                <label htmlFor="uemail">Email *</label>
                <input id="uemail" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div>
                <label htmlFor="uname">Full name *</label>
                <input id="uname" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </div>
              <div>
                <label htmlFor="upass">Initial password (min 8) *</label>
                <input id="upass" type="password" required minLength={8} value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div>
                <label htmlFor="urole">Role</label>
                <select id="urole" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
                  <option value="employee">employee</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <div>
                <label htmlFor="udept">Department</label>
                <input id="udept" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
              </div>
              <div>
                <label htmlFor="utitle">Job title</label>
                <input id="utitle" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} />
              </div>
            </div>
            <div className="form-actions">
              <button className="primary" type="submit" disabled={busy}>Create account</button>
            </div>
            <p className="muted tiny">
              The password is never shown again — share it with the user out of band. The
              creation itself is recorded in the audit log.
            </p>
          </form>
        )}

        <div className="table-wrap" style={{ marginTop: 14 }}>
          <table>
            <thead>
              <tr>
                <th>User</th><th>Role</th><th>Department</th><th>Consent</th><th>Device</th><th>State</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.full_name}</strong>
                    <div className="muted tiny">{user.email}</div>
                  </td>
                  <td><span className={`badge ${user.role === "admin" ? "purple" : "blue"}`}>{user.role}</span></td>
                  <td>{user.department ?? "—"}</td>
                  <td>
                    {user.consent_accepted ? (
                      <span className="badge green" title={`policy ${user.consent_version}`}>
                        consented {user.consent_at ? new Date(user.consent_at).toLocaleDateString() : ""}
                      </span>
                    ) : (
                      <span className="badge amber">not consented</span>
                    )}
                  </td>
                  <td className="tiny">{user.device_id ?? "—"}</td>
                  <td>
                    <span className={`badge ${user.is_active ? "green" : "red"}`}>
                      {user.is_active ? "active" : "disabled"}
                    </span>
                  </td>
                  <td>
                    {/* Backend also refuses self-deactivation (409). */}
                    <button className="small ghost" onClick={() => void toggleStatus(user)}>
                      {user.is_active ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
