import { useCallback, useEffect, useState } from "react";
import { api, type Alert, type AlertStatus, type Page } from "../../api/client";
import { SeverityBadge } from "../../components/RiskBadge";

const STATUSES = ["", "triggered", "acknowledged", "resolved", "false_positive"];
const SEVERITIES = ["", "critical", "high", "medium", "low"];
const PAGE_SIZE = 25;

const STATUS_LABEL: Record<AlertStatus, string> = {
  triggered: "Acknowledge",
  acknowledged: "Resolve",
  resolved: "Reopen",
  false_positive: "Reopen",
};

const NEXT_STATUS: Record<AlertStatus, AlertStatus> = {
  triggered: "acknowledged",
  acknowledged: "resolved",
  resolved: "triggered",
  false_positive: "triggered",
};

export default function Alerts() {
  const [data, setData] = useState<Page<Alert> | null>(null);
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(
        await api.alerts({
          page,
          page_size: PAGE_SIZE,
          status: status || undefined,
          severity: severity || undefined,
        }),
      );
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [page, status, severity]);

  useEffect(() => {
    void load();
  }, [load]);

  const transition = async (alert: Alert, next: AlertStatus) => {
    setBusyId(alert.id);
    try {
      await api.setAlertStatus(alert.id, next);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const markFalsePositive = async (alert: Alert) => {
    setBusyId(alert.id);
    try {
      await api.setAlertStatus(alert.id, "false_positive");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <h1>Alerts</h1>
      <p className="page-sub">
        High-confidence policy violations pushed in real time by the Celery alert
        pipeline (and over the live WebSocket you see in the corner).
      </p>

      <div className="card">
        <div className="filters" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="status">Status</label>
            <select id="status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              {STATUSES.map((s) => <option key={s} value={s}>{s || "all"}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="sev">Severity</label>
            <select id="sev" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }}>
              {SEVERITIES.map((s) => <option key={s} value={s}>{s || "all"}</option>)}
            </select>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        {!data?.items.length ? (
          <p className="muted">No alerts match. {data ? "Nothing needs a response right now." : "Loading…"}</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Severity</th>
                  <th>Title</th>
                  <th>User</th>
                  <th>Summary (redacted)</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((alert) => (
                  <tr key={alert.id}>
                    <td>{new Date(alert.created_at).toLocaleString()}</td>
                    <td><SeverityBadge severity={alert.severity} /></td>
                    <td>
                      <strong>{alert.title}</strong>
                      <div className="muted tiny">
                        {(alert.context as { rule?: string } | null)?.rule
                          ? `rule: ${(alert.context as { rule?: string }).rule}`
                          : "default policy"}
                      </div>
                    </td>
                    <td>{alert.user_email ?? alert.user_id.slice(0, 8)}</td>
                    <td className="preview-cell">{alert.summary}</td>
                    <td><span className="badge blue">{alert.status.replace("_", " ")}</span></td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button
                          className="small"
                          disabled={busyId === alert.id}
                          onClick={() => void transition(alert, NEXT_STATUS[alert.status])}
                        >
                          {STATUS_LABEL[alert.status]}
                        </button>
                        {alert.status === "triggered" && (
                          <button
                            className="small ghost"
                            disabled={busyId === alert.id}
                            onClick={() => void markFalsePositive(alert)}
                          >
                            False positive
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pagination">
          <span>{data ? `${data.total} alerts` : "…"}</span>
          <div className="buttons">
            <button className="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
            <button className="small" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        </div>
      </div>
    </>
  );
}
