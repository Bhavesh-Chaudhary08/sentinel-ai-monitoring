import { useCallback, useEffect, useState } from "react";
import { api, type PolicyRule } from "../../api/client";
import { ActionBadge, CategoryBadge } from "../../components/RiskBadge";

const EMPTY_FORM = {
  name: "",
  description: "",
  category: "",
  action: "log_only" as PolicyRule["action"],
  min_confidence: 0.7,
  priority: 100,
  role_scope: "",
  department_scope: "",
  warn_message: "",
  block_message: "",
};

export default function Policies() {
  const [rules, setRules] = useState<PolicyRule[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const page = await api.rules();
      setRules(page.items);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startEdit = (rule: PolicyRule) => {
    setEditingId(rule.id);
    setForm({
      name: rule.name,
      description: rule.description ?? "",
      category: rule.category ?? "",
      action: rule.action,
      min_confidence: rule.min_confidence,
      priority: rule.priority,
      role_scope: rule.role_scope ?? "",
      department_scope: rule.department_scope ?? "",
      warn_message: rule.warn_message ?? "",
      block_message: rule.block_message ?? "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const submit = async () => {
    if (!form.name.trim()) {
      setError("Rule name is required");
      return;
    }
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      description: form.description || null,
      category: (form.category || null) as PolicyRule["category"],
      action: form.action,
      min_confidence: Number(form.min_confidence),
      priority: Number(form.priority),
      role_scope: (form.role_scope || null) as PolicyRule["role_scope"],
      department_scope: form.department_scope || null,
      warn_message: form.warn_message || null,
      block_message: form.block_message || null,
    } as Partial<PolicyRule>;
    try {
      if (editingId) await api.updateRule(editingId, payload);
      else await api.createRule(payload);
      resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const deactivate = async (rule: PolicyRule) => {
    try {
      await api.deactivateRule(rule.id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const reactivate = async (rule: PolicyRule) => {
    try {
      await api.updateRule(rule.id, { is_active: true } as Partial<PolicyRule>);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <>
      <h1>Policy engine</h1>
      <p className="page-sub">
        Per-category enforcement: <code>log_only</code> → <code>warn</code> →{" "}
        <code>block</code>. Role/department-scoped rules override global ones; ties break
        by priority. Blocks are enforced <strong>pre-send</strong> by the extension.
      </p>

      <div className="card">
        <h2>{editingId ? "Edit rule" : "Create rule"}</h2>
        {error && <p className="error">{error}</p>}
        <div className="form-grid">
          <div>
            <label htmlFor="rname">Name *</label>
            <input id="rname" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Block secrets in prompts" />
          </div>
          <div>
            <label htmlFor="rcat">Category</label>
            <select id="rcat" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="">(any category)</option>
              <option value="credentials">credentials</option>
              <option value="pii">pii</option>
              <option value="financial">financial</option>
              <option value="confidential">confidential</option>
              <option value="source_code">source_code</option>
              <option value="other">other</option>
            </select>
          </div>
          <div>
            <label htmlFor="raction">Action</label>
            <select id="raction" value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value as PolicyRule["action"] })}>
              <option value="log_only">log only</option>
              <option value="warn">warn</option>
              <option value="block">block</option>
            </select>
          </div>
          <div>
            <label htmlFor="rconf">Min confidence (0–1)</label>
            <input id="rconf" type="number" step="0.05" min="0" max="1" value={form.min_confidence}
              onChange={(e) => setForm({ ...form, min_confidence: Number(e.target.value) })} />
          </div>
          <div>
            <label htmlFor="rprio">Priority (higher wins)</label>
            <input id="rprio" type="number" min="0" max="1000" value={form.priority}
              onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} />
          </div>
          <div>
            <label htmlFor="rrole">Role override</label>
            <select id="rrole" value={form.role_scope} onChange={(e) => setForm({ ...form, role_scope: e.target.value })}>
              <option value="">(everyone)</option>
              <option value="admin">admin</option>
              <option value="employee">employee</option>
            </select>
          </div>
          <div>
            <label htmlFor="rdept">Department override</label>
            <input id="rdept" value={form.department_scope} onChange={(e) => setForm({ ...form, department_scope: e.target.value })} placeholder="Finance" />
          </div>
          <div>
            <label htmlFor="rdesc">Description</label>
            <input id="rdesc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div>
            <label htmlFor="rwarn">Warn message (shown to employee)</label>
            <input id="rwarn" value={form.warn_message} onChange={(e) => setForm({ ...form, warn_message: e.target.value })} />
          </div>
          <div>
            <label htmlFor="rblock">Block message (shown in overlay)</label>
            <input id="rblock" value={form.block_message} onChange={(e) => setForm({ ...form, block_message: e.target.value })} />
          </div>
        </div>
        <div className="form-actions">
          <button className="primary" disabled={busy} onClick={() => void submit()}>
            {editingId ? "Save changes" : "Create rule"}
          </button>
          {editingId && <button className="ghost" onClick={resetForm}>Cancel edit</button>}
        </div>
      </div>

      <div className="card">
        <h2>Active &amp; inactive rules</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Priority</th><th>Name</th><th>Match</th><th>Action</th><th>Conf ≥</th><th>Scope</th><th>State</th><th></th>
              </tr>
            </thead>
            <tbody>
              {[...rules]
                .sort((a, b) => b.priority - a.priority)
                .map((rule) => (
                  <tr key={rule.id} className={rule.is_active ? "" : "muted"}>
                    <td>{rule.priority}</td>
                    <td>
                      <strong>{rule.name}</strong>
                      {rule.description && <div className="muted tiny">{rule.description}</div>}
                    </td>
                    <td>{rule.category ? <CategoryBadge category={rule.category} /> : <span className="badge gray">any</span>}</td>
                    <td><ActionBadge action={rule.action} /></td>
                    <td>{rule.min_confidence.toFixed(2)}</td>
                    <td>
                      {rule.role_scope && <span className="badge blue">{rule.role_scope}</span>}{" "}
                      {rule.department_scope && <span className="badge purple">{rule.department_scope}</span>}
                      {!rule.role_scope && !rule.department_scope && <span className="muted tiny">everyone</span>}
                    </td>
                    <td>
                      <span className={`badge ${rule.is_active ? "green" : "gray"}`}>
                        {rule.is_active ? "active" : "inactive"}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="small" onClick={() => startEdit(rule)}>Edit</button>
                        {rule.is_active ? (
                          <button className="small danger" onClick={() => void deactivate(rule)}>Deactivate</button>
                        ) : (
                          <button className="small ghost" onClick={() => void reactivate(rule)}>Reactivate</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              {!rules.length && (
                <tr><td colSpan={8} className="muted">No rules yet — create one above or run the seed script.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="muted tiny">
          Rules are deactivated rather than deleted so historical interactions keep
          their references.
        </p>
      </div>
    </>
  );
}
