import { useCallback, useEffect, useState } from "react";
import { api, type AuditEntry, type Page } from "../../api/client";

const PAGE_SIZE = 50;

export default function Audit() {
  const [data, setData] = useState<Page<AuditEntry> | null>(null);
  const [action, setAction] = useState("");
  const [draftAction, setDraftAction] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.audit(page, action || undefined));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [page, action]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <h1>Audit log</h1>
      <p className="page-sub">
        Append-only record of privileged actions: rule changes, alert decisions, exports,
        account lifecycle. This is what makes the monitor itself accountable.
      </p>

      <div className="card">
        <div className="filters" style={{ marginBottom: 14 }}>
          <div className="field grow">
            <label htmlFor="action">Action filter (exact)</label>
            <input
              id="action"
              placeholder="rule.create, export.csv, alert.status…"
              value={draftAction}
              onChange={(e) => setDraftAction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setAction(draftAction.trim());
                  setPage(1);
                }
              }}
            />
          </div>
          <div className="field">
            <button
              className="primary"
              onClick={() => {
                setAction(draftAction.trim());
                setPage(1);
              }}
            >
              Apply
            </button>
          </div>
          <div className="field">
            <button
              className="ghost"
              onClick={() => {
                setDraftAction("");
                setAction("");
                setPage(1);
              }}
            >
              Clear
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time (UTC)</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Target</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.created_at).toLocaleString()}</td>
                  <td>{entry.actor_email ?? entry.actor_id.slice(0, 8)}</td>
                  <td><span className="badge blue">{entry.action}</span></td>
                  <td className="tiny">
                    {entry.target_type ?? "—"}
                    {entry.target_id ? ` · ${entry.target_id.slice(0, 8)}` : ""}
                  </td>
                  <td className="tiny muted" style={{ wordBreak: "break-word" }}>
                    {entry.detail ? JSON.stringify(entry.detail) : "—"}
                  </td>
                </tr>
              ))}
              {data && !data.items.length && (
                <tr><td colSpan={5} className="muted">No audit entries match.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="pagination">
          <span>{data ? `${data.total} entries · page ${data.page} / ${totalPages}` : "…"}</span>
          <div className="buttons">
            <button className="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
            <button className="small" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        </div>
      </div>
    </>
  );
}
