import { useEffect, useMemo, useState } from "react";
import { api, type FocusOut, type TimeSegment, type TopDomainRow } from "../../api/client";
import WeeklyDigest from "../../components/WeeklyDigest";
import { fmtClock, fmtDelta, fmtDuration } from "../../lib/format";

/**
 * Admin browser-time view: team rollup + per-employee drilldown.
 *
 * Framing rule from the product spec: this is a *browser time report*, not a
 * proof-of-work score. Buckets are reported as facts ("no browser activity
 * 14:00–15:00"), never as verdicts.
 */

interface UserTotals {
  id: string;
  email: string;
  name: string;
  active: number;
  idle: number;
  other: number;
  away: number;
  audible: number;
}

function segmentLabel(seg: TimeSegment): { label: string; detail: string } {
  if (seg.kind === "away") {
    return seg.active_seconds > 0
      ? { label: "other activity", detail: "another app focused" }
      : { label: "away", detail: "no keyboard/mouse input" };
  }
  if (!seg.domain) return { label: "browser", detail: "internal page" };
  return { label: seg.domain, detail: seg.page_path ?? "/" };
}

export default function Activity() {
  const [days, setDays] = useState(7);
  const [team, setTeam] = useState<Awaited<ReturnType<typeof api.activityTeamDaily>>>([]);
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [domains, setDomains] = useState<TopDomainRow[]>([]);
  const [segments, setSegments] = useState<TimeSegment[]>([]);
  const [trends, setTrends] = useState<Awaited<ReturnType<typeof api.activityTrends>> | null>(null);
  const [focus, setFocus] = useState<FocusOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .activityTeamDaily(days)
      .then((rows) => {
        setTeam(rows);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));
  }, [days]);

  const users = useMemo(() => {
    const map = new Map<string, UserTotals>();
    for (const row of team) {
      const u =
        map.get(row.user_id) ??
        ({ id: row.user_id, email: row.user_email, name: row.user_name, active: 0, idle: 0, other: 0, away: 0, audible: 0 } as UserTotals);
      u.active += row.browser_active_seconds;
      u.idle += row.browser_idle_seconds;
      u.other += row.other_seconds;
      u.away += row.away_seconds;
      u.audible += row.audible_seconds;
      map.set(row.user_id, u);
    }
    return Array.from(map.values()).sort((a, b) => a.email.localeCompare(b.email));
  }, [team]);

  useEffect(() => {
    api
      .activityTrends(days, selectedUser ?? undefined)
      .then((t) => setTrends(t))
      .catch((err) => setError((err as Error).message));
  }, [days, selectedUser]);

  useEffect(() => {
    if (!selectedUser) {
      setDomains([]);
      setSegments([]);
      setFocus(null);
      return;
    }
    Promise.all([
      api.activityTopDomains(days, selectedUser),
      api.activitySegments(days, selectedUser, 100),
      api.activityFocus(days, selectedUser),
    ])
      .then(([d, s, f]) => {
        setDomains(d);
        setSegments(s);
        setFocus(f);
      })
      .catch((err) => setError((err as Error).message));
  }, [selectedUser, days]);

  const totals = users.reduce(
    (acc, u) => ({
      active: acc.active + u.active,
      other: acc.other + u.other,
      away: acc.away + u.away,
    }),
    { active: 0, other: 0, away: 0 },
  );

  const selectedDays = selectedUser
    ? team.filter((row) => row.user_id === selectedUser).sort((a, b) => b.date.localeCompare(a.date))
    : [];

  // Whose numbers the trends card is showing — team by default, the drilled-
  // down person otherwise (scope comes from the endpoint's user_id handling).
  const trendsScopeLabel = selectedUser
    ? users.find((u) => u.id === selectedUser)?.name ?? "selected employee"
    : "team";

  return (
    <>
      <h1>Browser time</h1>
      <p className="page-sub">
        Where browser hours actually went, per person — reported as durations, not
        verdicts. "Other activity" means the employee was at the keyboard with a
        different app focused; "away" means no keyboard/mouse input at all.
      </p>

      <div className="filters" style={{ marginBottom: 8 }}>
        <div className="field">
          <label htmlFor="range">Date range</label>
          <select id="range" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>last 7 days</option>
            <option value={30}>last 30 days</option>
            <option value={90}>last 90 days</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="emp">Employee</label>
          <select
            id="emp"
            value={selectedUser ?? ""}
            onChange={(e) => setSelectedUser(e.target.value || null)}
          >
            <option value="">— select to drill down —</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="value">{fmtDuration(totals.active)}</div>
          <div className="label">browser active · team · {days}d</div>
        </div>
        <div className="stat-card">
          <div className="value">{fmtDuration(totals.other)}</div>
          <div className="label">other activity (other apps)</div>
        </div>
        <div className="stat-card">
          <div className="value">{fmtDuration(totals.away)}</div>
          <div className="label">away from keyboard</div>
        </div>
        <div className="stat-card">
          <div className="value">{users.length}</div>
          <div className="label">people with tracked time</div>
        </div>
      </div>

      <div className="card">
        <h2>Team totals — last {days} days</h2>
        {users.length === 0 ? (
          <p className="muted">
            No browser time recorded yet. Tracking starts once employees are enrolled
            and consented in the extension (same gate as AI capture).
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Browser active</th>
                <th>Browser idle</th>
                <th>Other activity</th>
                <th>Away</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => setSelectedUser(u.id)}
                >
                  <td>
                    <strong>{u.name}</strong>
                    <div className="muted tiny">{u.email}</div>
                  </td>
                  <td>{fmtDuration(u.active)}</td>
                  <td>{fmtDuration(u.idle)}</td>
                  <td>{fmtDuration(u.other)}</td>
                  <td>{fmtDuration(u.away)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Trends — last {days} days vs previous {days} days · {trendsScopeLabel}</h2>
        {!trends ? (
          <p className="muted">Loading comparison…</p>
        ) : trends.current.segments === 0 && trends.previous.segments === 0 ? (
          <p className="muted">
            Nothing to compare yet — neither this window nor the one before it
            contains browser time.
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
                <div className="value">{fmtDuration(trends.focus.avg_focus_block_seconds)}</div>
                <div className="label">average focus block</div>
              </div>
              <div className="stat-card">
                <div className="value">{fmtDuration(trends.focus.longest_focus_seconds)}</div>
                <div className="label">longest focus block</div>
              </div>
            </div>
            <p className="muted tiny">
              A focus block is contiguous focused time on one domain (a gap over 2
              minutes ends it); a context switch is moving to a different domain
              without a break. Browser behaviour only — this says where time went,
              not how good the work was.
            </p>
          </>
        )}
      </div>

      {trends && trends.scope === "team" && trends.users.length > 0 && (
        <div className="card">
          <h2>Per-person change — last {days} days vs previous {days}</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>This period</th>
                <th>Previous period</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {trends.users.map((u) => (
                <tr
                  key={u.user_id}
                  style={{ cursor: "pointer" }}
                  onClick={() => setSelectedUser(u.user_id)}
                >
                  <td>
                    <strong>{u.user_name}</strong>
                    <div className="muted tiny">{u.user_email}</div>
                  </td>
                  <td>{fmtDuration(u.current.browser_active_seconds)}</td>
                  <td>{fmtDuration(u.previous.browser_active_seconds)}</td>
                  <td>{fmtDelta(u.delta_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {trends && trends.scope === "team" && trends.daily.length > 0 && (
        <div className="card">
          <h2>Daily totals — team, current window</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Browser active</th>
                <th>Other activity</th>
                <th>Away</th>
                <th>Media</th>
              </tr>
            </thead>
            <tbody>
              {trends.daily.map((d) => (
                <tr key={d.date}>
                  <td>{d.date}</td>
                  <td>{fmtDuration(d.browser_active_seconds)}</td>
                  <td>{fmtDuration(d.other_seconds)}</td>
                  <td>{fmtDuration(d.away_seconds)}</td>
                  <td>{fmtDuration(d.audible_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedUser && (
        <>
          <div className="card">
            <h2>Focus score · {focus?.user_name ?? "selected employee"}</h2>
            {!focus ? (
              <p className="muted">Loading focus…</p>
            ) : focus.days.length === 0 ? (
              <p className="muted">No browser time recorded in this window.</p>
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
                      <th>Share</th>
                      <th>Continuity</th>
                      <th>Calm</th>
                      <th>Focused time</th>
                      <th>Blocks</th>
                      <th>Switches</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...focus.days].reverse().map((row) => (
                      <tr key={row.date}>
                        <td>{row.date}</td>
                        <td>{row.focus_score ?? "—"}</td>
                        <td>{row.components ? `${row.components.share_pct}%` : "—"}</td>
                        <td>{row.components ? `${row.components.continuity_pct}%` : "—"}</td>
                        <td>{row.components ? `${row.components.calm_pct}%` : "—"}</td>
                        <td>{fmtDuration(row.focus_seconds)}</td>
                        <td>{row.focus_blocks}</td>
                        <td>{row.context_switches}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted tiny">
                  Per-person by design — the API deliberately has no team focus
                  ranking. Score = focus share (45) + sustained blocks (30) + few
                  switches (25); away time never counts against it, and “—” means
                  no focused-tab time that day, not a zero. Same numbers the
                  employee sees on their My time page.
                </p>
              </>
            )}
          </div>

          <WeeklyDigest
            userId={selectedUser}
            heading={`Weekly digest · ${focus?.user_name ?? "selected employee"}`}
          />

          <div className="card">
            <h2>Daily breakdown</h2>
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
                {selectedDays.map((row) => (
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
              Domain + path only — query strings never leave the employee's device.
            </p>
            <table className="table">
              <thead>
                <tr><th>Start</th><th>What</th><th>Detail</th><th>Duration</th></tr>
              </thead>
              <tbody>
                {segments.map((seg) => {
                  const { label, detail } = segmentLabel(seg);
                  return (
                    <tr key={seg.id}>
                      <td>{new Date(seg.started_at).toLocaleString()}</td>
                      <td>{label}</td>
                      <td className="muted">{detail}</td>
                      <td>{fmtDuration(seg.active_seconds + seg.idle_seconds)} · {fmtClock(seg.started_at)}–{fmtClock(seg.ended_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
