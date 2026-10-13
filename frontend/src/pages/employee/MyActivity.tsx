import { useCallback, useEffect, useState } from "react";
import { api, downloadFile, exportPath, type Interaction, type UsageOut } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { InteractionDetailModal, InteractionTable } from "../../components/InteractionTable";

const CATEGORIES = ["", "pii", "source_code", "financial", "confidential", "credentials"];

export default function MyActivity() {
  const { user, refresh } = useAuth();
  const [items, setItems] = useState<Interaction[]>([]);
  const [usage, setUsage] = useState<UsageOut | null>(null);
  const [category, setCategory] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [page, stats] = await Promise.all([
        api.interactions({
          page: 1,
          page_size: 50,
          category: category || undefined,
          flagged: flaggedOnly ? true : undefined,
        }),
        api.usage(30),
      ]);
      setItems(page.items);
      setUsage(stats);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [category, flaggedOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const consented = !!user?.consent_accepted && !!user?.is_enrolled;

  return (
    <>
      <h1>My activity</h1>
      <p className="page-sub">
        Everything recorded from your account — full transparency over what the
        extension captures and what the classifier decided.
      </p>

      <div className="card">
        <div className="modal-head">
          <h2>Monitoring status</h2>
          <span className={`monitor-pill ${consented ? "on" : "off"}`}>
            <span className="dot" />
            {consented ? "Monitoring ON" : "Monitoring off"}
          </span>
        </div>
        {consented ? (
          <dl className="kv">
            <dt>Account</dt><dd>{user?.email}</dd>
            <dt>Consent policy</dt><dd>version {user?.consent_version ?? "—"} · accepted {user?.consent_at ? new Date(user.consent_at).toLocaleString() : "—"}</dd>
            <dt>Enrolled device</dt><dd>{user?.device_id ?? "—"} · extension {user?.extension_version ?? "—"}</dd>
            <dt>Data policy</dt>
            <dd>
              Full prompt/response text is stored <strong>only when flagged</strong>;
              everything else keeps a SHA-256 hash + PII-masked preview, purged per
              retention policy.
            </dd>
          </dl>
        ) : (
          <p className="muted">
            Capture is not active. Open the extension popup, sign in with your org
            account and accept the monitoring notice — the indicator turns green
            everywhere once enabled.
          </p>
        )}
        <div className="form-actions">
          <button className="ghost small" onClick={() => void refresh()}>Refresh status</button>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="value">{usage?.totals.interactions ?? "—"}</div>
          <div className="label">your messages · last {usage?.days ?? 30}d</div>
        </div>
        <div className="stat-card">
          <div className="value">{usage?.totals.flagged ?? "—"}</div>
          <div className="label">flagged by DLP</div>
        </div>
        <div className="stat-card">
          <div className="value">{usage?.totals.blocked ?? "—"}</div>
          <div className="label">blocked before send</div>
        </div>
      </div>

      <div className="card">
        <div className="modal-head">
          <h2>Your logged interactions</h2>
          <button
            className="small ghost"
            onClick={() => void downloadFile(exportPath("csv", {}), "my-activity.csv")}
          >
            Export my data (CSV)
          </button>
        </div>

        <div className="filters" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="cat">Category</label>
            <select id="cat" value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c || "all"}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="flag">Scope</label>
            <select
              id="flag"
              value={flaggedOnly ? "flagged" : "all"}
              onChange={(e) => setFlaggedOnly(e.target.value === "flagged")}
            >
              <option value="all">all activity</option>
              <option value="flagged">flagged only</option>
            </select>
          </div>
        </div>

        {error && <p className="error">{error}</p>}
        <InteractionTable
          items={items}
          showUser={false}
          onSelect={(item) => setSelected(item.id)}
        />
        <p className="muted tiny">
          Show more via filters, or export the full set — your data, your view.
        </p>
      </div>

      {selected && (
        <InteractionDetailModal interactionId={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
