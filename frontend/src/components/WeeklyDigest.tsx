import { useEffect, useState } from "react";
import { api, digestExportPath, downloadFile, type DigestOut } from "../api/client";
import { fmtDuration } from "../lib/format";
import { currentWeekLabel, shiftWeekLabel } from "../lib/week";

/**
 * One person's week on a page (Phase 4) — the employee self-view and the
 * admin drilldown share this card. Same framing rules as the rest of the
 * browser-time work: durations are facts, the focus score is per-person with
 * no ranking surface, an unscored day shows "—" and never a fake 0, and the
 * export carries counts/durations only (never prompt text) and is audited.
 */
export default function WeeklyDigest({
  userId,
  heading,
}: {
  userId?: string; // admin drilldown: the selected employee; employee view: undefined (self)
  heading?: string;
}) {
  const [week, setWeek] = useState<string>(currentWeekLabel());
  const [digest, setDigest] = useState<DigestOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api
      .activityDigest(week, userId)
      .then((d) => {
        setDigest(d);
        setError(null);
      })
      .catch((err) => {
        setDigest(null);
        setError((err as Error).message);
      });
  }, [week, userId]);

  const onExport = async () => {
    if (!digest) return;
    setExporting(true);
    try {
      await downloadFile(digestExportPath(digest.week, userId), `digest-${digest.week}.csv`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setExporting(false);
    }
  };

  const atCurrentWeek = week === currentWeekLabel();
  const empty =
    digest &&
    digest.totals.segments === 0 &&
    digest.ai_usage.interactions === 0;

  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <h2 style={{ margin: 0 }}>
          {heading ?? "Weekly digest"}
          {digest ? ` · ${digest.week}` : ""}
        </h2>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            className="ghost"
            onClick={() => setWeek(shiftWeekLabel(week, -1))}
            aria-label="Previous week"
          >
            ◀
          </button>
          <button
            className="ghost"
            disabled={atCurrentWeek}
            onClick={() => setWeek(shiftWeekLabel(week, 1))}
            aria-label="Next week"
            title={atCurrentWeek ? "This is the current week" : "Next week"}
          >
            ▶
          </button>
          <button className="ghost" disabled={!digest || exporting} onClick={onExport}>
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

      {digest && (
        <p className="muted tiny" style={{ marginTop: 6 }}>
          week of {digest.week_start} – {digest.week_end} (UTC days)
        </p>
      )}

      {error && <p className="error">{error}</p>}

      {!digest && !error && <p className="muted">Loading digest…</p>}

      {empty ? (
        <p className="muted">
          Nothing tracked this week yet — the digest fills in once the extension
          is monitoring this account (browser time and AI prompts both count).
        </p>
      ) : (
        digest && (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="value">{digest.focus.average_score ?? "—"}</div>
                <div className="label">
                  focus average · days with focused-tab time
                  {digest.focus.average_score === null && " (none yet)"}
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{digest.focus.best_day_score ?? "—"}</div>
                <div className="label">
                  best day{digest.focus.best_day ? ` · ${digest.focus.best_day}` : ""}
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{fmtDuration(digest.totals.browser_active_seconds)}</div>
                <div className="label">browser active this week</div>
              </div>
              <div className="stat-card">
                <div className="value">{digest.tracked_days}</div>
                <div className="label">days with tracked time</div>
              </div>
              <div className="stat-card">
                <div className="value">{digest.ai_usage.interactions}</div>
                <div className="label">
                  AI prompts captured · {digest.ai_usage.flagged} flagged ·{" "}
                  {digest.ai_usage.blocked} blocked
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{fmtDuration(digest.totals.away_seconds)}</div>
                <div className="label">away (counts against nothing)</div>
              </div>
            </div>

            {digest.days.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Score</th>
                    <th>Browser active</th>
                    <th>Focused time</th>
                    <th>Blocks</th>
                    <th>Switches</th>
                  </tr>
                </thead>
                <tbody>
                  {[...digest.days].reverse().map((row) => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>{row.focus_score ?? "—"}</td>
                      <td>{fmtDuration(row.browser_active_seconds)}</td>
                      <td>{fmtDuration(row.focus_seconds)}</td>
                      <td>{row.focus_blocks}</td>
                      <td>{row.context_switches}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {digest.top_domains.length > 0 && (
              <table className="table">
                <thead>
                  <tr><th>Top domain</th><th>Focused time</th></tr>
                </thead>
                <tbody>
                  {digest.top_domains.map((d) => (
                    <tr key={d.domain}>
                      <td>{d.domain}</td>
                      <td>{fmtDuration(d.seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <p className="muted tiny">
              {digest.ai_usage.by_tool.length > 0 ? (
                <>
                  AI tools this week:{" "}
                  {digest.ai_usage.by_tool.map((t) => `${t.key} ×${t.count}`).join(" · ")}
                  {digest.ai_usage.alerts > 0 && ` · ${digest.ai_usage.alerts} alert(s)`}.{" "}
                </>
              ) : (
                <>No AI prompts captured this week.{" "}
              </>
              )}
              One person's week — same numbers as everywhere else, no team
              ranking. The focus score describes browser focus only, not the
              quality of the work; away time counts against nothing; “—” means
              nothing to score, never a zero. The CSV export is audited and
              carries counts and durations only — never prompt text.
            </p>
          </>
        )
      )}
    </div>
  );
}
