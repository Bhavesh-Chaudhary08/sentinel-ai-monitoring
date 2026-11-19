import { useEffect, useState } from "react";
import { api, type Interaction, type InteractionDetail } from "../api/client";
import { ActionBadge, CategoryBadge, RiskBadge, ScoreBadge } from "./RiskBadge";

interface TableProps {
  items: Interaction[];
  showUser?: boolean;
  onSelect?: (item: Interaction) => void;
}

export function InteractionTable({ items, showUser = true, onSelect }: TableProps) {
  if (!items.length) {
    return <p className="muted">No interactions match these filters.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time (UTC)</th>
            {showUser && <th>User</th>}
            <th>Tool</th>
            <th>Domain</th>
            <th>Category</th>
            <th>Score</th>
            <th>Action</th>
            <th>Preview (redacted)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              className={`clickable ${item.is_flagged ? "row-flagged" : ""}`}
              onClick={() => onSelect?.(item)}
            >
              <td>{new Date(item.occurred_at).toLocaleString()}</td>
              {showUser && <td>{item.user_email ?? item.user_id.slice(0, 8)}</td>}
              <td>{item.ai_tool}</td>
              <td>
                {item.domain}
                {!item.is_known_platform && (
                  <>
                    {" "}
                    <span className="badge amber">shadow</span>
                    {item.is_first_seen && <span className="badge blue">first seen</span>}
                  </>
                )}
              </td>
              <td><CategoryBadge category={item.risk_category} /></td>
              <td><ScoreBadge score={item.risk_score} flagged={item.is_flagged} /></td>
              <td>
                <ActionBadge action={item.applied_action} status={item.classification_status} />
                {item.was_blocked && <span className="badge red">sent-blocked</span>}
              </td>
              <td className="preview-cell">{item.redacted_preview ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Detail modal: full metadata, findings ("why it was flagged"), stored text. */
export function InteractionDetailModal({
  interactionId,
  onClose,
}: {
  interactionId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<InteractionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .interaction(interactionId)
      .then((d) => !cancelled && setDetail(d))
      .catch((err) => !cancelled && setError((err as Error).message));
    return () => {
      cancelled = true;
    };
  }, [interactionId]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Interaction detail</h2>
          <button className="small ghost" onClick={onClose}>Close</button>
        </div>

        {error && <p className="error">{error}</p>}
        {!detail && !error && <p className="muted">Loading…</p>}

        {detail && (
          <div className="modal-body detail-grid">
            <section>
            <h3 className="section-label">Metadata</h3>
            <dl className="kv">
              <dt>User</dt><dd>{detail.user_email ?? detail.user_id}</dd>
              <dt>Tool / domain</dt><dd>{detail.ai_tool} · {detail.domain}{detail.page_path ?? ""}</dd>
              <dt>Captured</dt><dd>{new Date(detail.occurred_at).toLocaleString()}</dd>
              <dt>Classification</dt>
              <dd>
                <CategoryBadge category={detail.risk_category} />{" "}
                <ScoreBadge score={detail.risk_score} flagged={detail.is_flagged} />{" "}
                <span className="muted">via {detail.classifier_version ?? "pending"}</span>
                {" "}· status {detail.classification_status}
              </dd>
              <dt>Policy</dt>
              <dd>
                <ActionBadge action={detail.applied_action} />
                {detail.was_blocked && <span className="badge red"> blocked client-side</span>}
                {detail.policy_rule_id && (
                  <span className="muted"> rule {detail.policy_rule_id.slice(0, 8)}</span>
                )}
              </dd>
              <dt>Known platform</dt>
              <dd>
                {detail.is_known_platform ? "yes" : "no"}
                {!detail.is_known_platform && (
                  <> <RiskBadge risk={detail.shadow_risk} />{detail.is_first_seen && " · first-seen access"}</>
                )}
              </dd>
              <dt>Retention</dt>
              <dd>
                {detail.content_stored ? (
                  <>raw text stored until <strong>{detail.purge_after ? new Date(detail.purge_after).toLocaleDateString() : "n/a"}</strong></>
                ) : (
                  "hash + masked preview only (raw text never stored)"
                )}
              </dd>
              <dt>Prompt hash</dt><dd className="tiny">{detail.prompt_hash ?? "—"}</dd>
            </dl>
            </section>

            <section>
            <h3 className="section-label">Why it was flagged</h3>
            {detail.findings.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Engine</th><th>Label</th><th>Score</th><th>Offsets</th></tr>
                  </thead>
                  <tbody>
                    {detail.findings.map((f) => (
                      <tr key={f.id}>
                        <td>{f.engine}</td>
                        <td>{f.label}</td>
                        <td>{f.score.toFixed(2)}</td>
                        <td>{f.start ?? "—"}–{f.end ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">No individual findings recorded.</p>
            )}

            {detail.prompt_text && (
              <>
                <h3 className="section-label" style={{ marginTop: 16 }}>
                  Stored prompt text (flagged)
                </h3>
                <div className="code-block">{detail.prompt_text}</div>
              </>
            )}
            {detail.response_text && (
              <>
                <h3 className="section-label" style={{ marginTop: 16 }}>
                  Stored response text (flagged)
                </h3>
                <div className="code-block">{detail.response_text}</div>
              </>
            )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
