import { useEffect, useState } from "react";
import { api, type ShadowDomain } from "../../api/client";
import { RiskBadge } from "../../components/RiskBadge";

export default function ShadowAI() {
  const [domains, setDomains] = useState<ShadowDomain[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .shadowAi()
      .then((rows) => {
        setDomains(rows);
        setError(null);
      })
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <h1>Shadow-AI discovery</h1>
      <p className="page-sub">
        First-time access to AI domains your allowlist doesn't recognize — detected by the
        extension's marker probe (domain + UI markers only, never page content), risk-rated
        by an explainable heuristic, and shown with who hit what.
      </p>

      <div className="card">
        {error && <p className="error">{error}</p>}
        {loading && <p className="muted">Loading…</p>}

        {!loading && !error && !domains.length && (
          <p className="muted">
            No unrecognized AI domains seen yet. Add domains to{" "}
            <code>KNOWN_AI_DOMAINS</code> when you adopt a tool, and this list stays clean.
          </p>
        )}

        {!!domains.length && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Domain</th>
                  <th>Risk</th>
                  <th>First seen</th>
                  <th>Last seen</th>
                  <th>Users</th>
                  <th>Interactions</th>
                </tr>
              </thead>
              <tbody>
                {domains.map((row) => (
                  <tr key={row.domain}>
                    <td><strong>{row.domain}</strong></td>
                    <td><RiskBadge risk={row.risk} /></td>
                    <td>{new Date(row.first_seen).toLocaleString()}</td>
                    <td>{new Date(row.last_seen).toLocaleString()}</td>
                    <td>{row.users}</td>
                    <td>{row.interactions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="muted tiny" style={{ marginTop: 12 }}>
          Risk heuristic: brand-impersonation hostnames and disposable TLDs → high;
          working chat composer + send button on an unknown host → medium; AI-ish naming →
          medium; otherwise low. See docs/threat-model.md.
        </p>
      </div>
    </>
  );
}
