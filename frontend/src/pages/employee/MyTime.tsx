import { useEffect, useState } from "react";
import { api, type FocusOut, type TimeSegment, type TopDomainRow } from "../../api/client";
import { fmtClock, fmtDelta, fmtDuration } from "../../lib/format";

/**
 * Employee self-view of the SAME browser-time data the admin sees — the
 * transparency differentiator. Same framing: durations, not verdicts.
 */
export default function MyTime() {
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof api.activityMe>> | null>(null);
  const [domains, setDomains] = useState<TopDomainRow[]>([]);
  const [segments, setSegments] = useState<TimeSegment[]>([]);
  const [trends, setTrends] = useState<Awaited<ReturnType<typeof api.activityTrends>> | null>(null);
  const [focus, setFocus] = useState<FocusOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.activityMe(days),
      api.activityTopDomains(days),
      api.activitySegments(days, undefined, 50),
      api.activityTrends(days),
      api.activityFocus(days),
    ])
      .then(([me, d, s, t, f]) => {
        setSummary(me);
        setDomains(d);
        setSegments(s);
        setTrends(t);
        setFocus(f);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));
  }, [days]);

  const sum = (pick: (d: NonNullable<typeof summary>["days"][number]) => number) =>
    (summary?.days ?? []).reduce((acc, d) => acc + pick(d), 0);

  // Most recent day that actually has a score (days are ascending from the API).
  const latestFocus = [...(focus?.days ?? [])]
    .reverse()
    .find((d) => d.focus_score !== null);

  return (
    <>
      <h1>My time</h1>
      <p className="page-sub">
        Exactly the same browser-time data your admin sees — nothing more, nothing
        less. This is a browser time report, not a score: it measures where browser
        hours went, and says nothing about the quality of your work.
      </p>

      <div className="filters" style={{ marginBottom: 8 }}>
        <div className="field">
          <label htmlFor="range">Date range</label>
          <select id="range" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>last 7 days</option>
            <option value={30}>last 30 days</option>
          </select>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="value">{fmtDuration(sum((d) => d.browser_active_seconds))}</div>
          <div className="label">browser active · last {days}d</div>
        </div>
        <div className="stat-card">
          <div className="value">{fmtDuration(sum((d) => d.other_seconds))}</div>
          <div className="label">other apps (at keyboard)</div>
        </div>
        <div className="stat-card">
          <div className="value">{fmtDuration(sum((d) => d.away_seconds))}</div>
          <div className="label">away from keyboard</div>
        </div>
        <div className="stat-card">
          <div className="value">{fmtDuration(sum((d) => d.audible_seconds))}</div>
          <div className="label">media playing</div>
        </div>
      </div>

      <div className="card">
        <h2>Trends — last {days} days vs previous {days} days</h2>
        {!trends ? (
          <p className="muted">Loading comparison…</p>
        ) : trends.current.segments === 0 && trends.previous.segments === 0 ? (
          <p className="muted">
            Nothing to compare yet — neither this window nor the one before it
            contains browser time for you.
          </p>
        ) : (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="value">{fmtDuration(trends.current.browser_active_seconds)}</div>
                <div className="label">
                  browser active · {fmtDelta(trends.deltas.browser_active_seconds)} vs prior {days}d
                  (was {fmtDuration(trends.previous.browser_active_seconds)})
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{fmtDuration(trends.current.other_seconds)}</div>
                <div className="label">
                  other activity · {fmtDelta(trends.deltas.other_seconds)} vs prior {days}d
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{fmtDuration(trends.current.away_seconds)}</div>
                <div className="label">
                  away · {fmtDelta(trends.deltas.away_seconds)} vs prior {days}d
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{trends.focus.context_switches}</div>
                <div className="label">context switches · {trends.focus.switches_per_day}/day</div>
              </div>
              <div className="stat-card">
                <div className="value">{trends.focus.focus_blocks}</div>
                <div className="label">focus blocks</div>
              </div>
              <div className="stat-card">
                <div className="value">{fmtDuration(trends.focus.longest_focus_seconds)}</div>
                <div className="label">longest focus block</div>
              </div>
            </div>
            <p className="muted tiny">
              A focus block is contiguous focused time on one domain (a gap over 2
              minutes ends it); a context switch is moving to a different domain
              without a break. This is a browser-time report, not a score.
            </p>
          </>
        )}
      </div>

      <div className="card">
        <h2>Focus score — last {days} days</h2>
        {!focus ? (
          <p className="muted">Loading focus…</p>
        ) : focus.days.length === 0 ? (
          <p className="muted">
            No browser time yet — your focus score appears once the extension is
            monitoring your account.
          </p>
        ) : (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="value">{focus.average_score ?? "—"}</div>
                <div className="label">
                  average · days with focused-tab time
                  {focus.average_score === null && " (none yet)"}
                </div>
              </div>
              <div className="stat-card">
                <div className="value">{latestFocus?.focus_score ?? "—"}</div>
                <div className="label">
                  latest tracked day
                  {latestFocus?.components
                    ? ` · share ${latestFocus.components.share_pct} · continuity ${latestFocus.components.continuity_pct} · calm ${latestFocus.components.calm_pct}`
                    : ""}
                </div>
              </div>
              <div className="stat-card">
                <div className="value">
                  {focus.days.filter((d) => d.focus_score !== null).length}
                </div>
                <div className="label">days scored</div>
              </div>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Score</th>
                  <th>Focused time</th>
                  <th>Focus blocks</th>
                  <th>Switches</th>
                  <th>Longest block</th>
                </tr>
              </thead>
              <tbody>
                {[...focus.days].reverse().map((row) => (
                  <tr key={row.date}>
                    <td>{row.date}</td>
                    <td>{row.focus_score ?? "—"}</td>
                    <td>{fmtDuration(row.focus_seconds)}</td>
                    <td>{row.focus_blocks}</td>
                    <td>{row.context_switches}</td>
                    <td>{fmtDuration(row.longest_focus_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted tiny">
              Your score (0–100) = focus share of keyboard-tracked time (45 pts) +
              sustained blocks, 25-min average at full marks (30 pts) + few context
              switches, 12/day at full marks (25 pts). Away time — breaks, meetings,
              lunch — never counts against it, and a day with no focused-tab time
              shows “—” rather than a 0. It describes browser focus only, not the
              quality of your work.
            </p>
          </>
        )}
      </div>

      <div className="card">
        <h2>Daily breakdown</h2>
        {(summary?.days.length ?? 0) === 0 ? (
          <p className="muted">
            No browser time recorded yet — tracking starts once the extension shows
            "Monitoring ON" for your account.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Browser active</th>
                <th>Browser idle</th>
                <th>Other activity</th>
                <th>Away</th>
              </tr>
            </thead>
            <tbody>
              {[...(summary?.days ?? [])].reverse().map((row) => (
                <tr key={row.date}>
                  <td>{row.date}</td>
                  <td>{fmtDuration(row.browser_active_seconds)}</td>
                  <td>{fmtDuration(row.browser_idle_seconds)}</td>
                  <td>{fmtDuration(row.other_seconds)}</td>
                  <td>{fmtDuration(row.away_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Top domains</h2>
        {domains.length === 0 ? (
          <p className="muted">No focused-tab time in this window.</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Domain</th><th>Focused time</th></tr>
            </thead>
            <tbody>
              {domains.map((d) => (
                <tr key={d.domain}>
                  <td>{d.domain}</td>
                  <td>{fmtDuration(d.seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Recent segments</h2>
        <p className="muted tiny">
          Only the domain and path are recorded — what you type is never captured
          here, and query strings stay on your device.
        </p>
        <table className="table">
          <thead>
            <tr><th>Start</th><th>What</th><th>Duration</th></tr>
          </thead>
          <tbody>
            {segments.map((seg) => (
              <tr key={seg.id}>
                <td>{new Date(seg.started_at).toLocaleString()}</td>
                <td>
                  {seg.kind === "away"
                    ? seg.active_seconds > 0
                      ? "other activity (another app)"
                      : "away"
                    : seg.domain
                      ? `${seg.domain}${seg.page_path && seg.page_path !== "/" ? seg.page_path : ""}`
                      : "browser internal page"}
                </td>
                <td>
                  {fmtDuration(seg.active_seconds + seg.idle_seconds)} · {fmtClock(seg.started_at)}–{fmtClock(seg.ended_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
