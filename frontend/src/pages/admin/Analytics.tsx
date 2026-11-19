import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type UsageOut } from "../../api/client";
import { CategoryBadge } from "../../components/RiskBadge";

const TOOL_COLORS = ["#00e599", "#3ecfff", "#a78bfa", "#f5b544", "#ff6b6b", "#6a6f77"];
const CATEGORY_COLORS: Record<string, string> = {
  none: "#6a6f77",
  pii: "#a78bfa",
  source_code: "#3ecfff",
  financial: "#f5b544",
  confidential: "#ff6b6b",
  credentials: "#ff6b6b",
  other: "#8c929a",
};
const TOOLTIP_STYLE = {
  background: "#121316",
  border: "1px solid #26282c",
  borderRadius: 8,
  fontSize: 12,
  color: "#e6e8eb",
} as const;

export default function Analytics() {
  const [days, setDays] = useState(30);
  const [usage, setUsage] = useState<UsageOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .usage(days)
      .then((data) => {
        setUsage(data);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));
  }, [days]);

  const totals = usage?.totals;

  return (
    <>
      <h1>Usage analytics</h1>
      <p className="page-sub">
        Org-wide adoption, DLP outcomes and shadow-AI discovery — aggregated from the
        interaction log.
      </p>

      <div className="filters" style={{ marginBottom: 8 }}>
        <div className="field">
          <label htmlFor="range">Date range</label>
          <select id="range" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>last 7 days</option>
            <option value={30}>last 30 days</option>
            <option value={90}>last 90 days</option>
            <option value={365}>last year</option>
          </select>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="stats-grid">
        <div className="stat-card"><div className="value">{totals?.interactions ?? "—"}</div><div className="label">captured messages</div></div>
        <div className="stat-card"><div className="value">{totals?.flagged ?? "—"}</div><div className="label">flagged by DLP</div></div>
        <div className="stat-card"><div className="value">{totals?.blocked ?? "—"}</div><div className="label">blocked pre-send</div></div>
        <div className="stat-card"><div className="value">{totals?.shadow_domains ?? "—"}</div><div className="label">shadow-AI domains</div></div>
        <div className="stat-card"><div className="value">{totals?.active_users ?? "—"}</div><div className="label">active users</div></div>
      </div>

      <div className="card">
        <h2>Daily volume — total vs flagged vs blocked</h2>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={usage?.by_day ?? []}>
            <defs>
              <linearGradient id="totalG" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00e599" stopOpacity={0.32} />
                <stop offset="95%" stopColor="#00e599" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="flagG" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ff6b6b" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#ff6b6b" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1c1d20" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" stroke="#3a3d42" tick={{ fill: "#6a6f77" }} fontSize={11} />
            <YAxis stroke="#3a3d42" tick={{ fill: "#6a6f77" }} fontSize={11} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: "#2a2c30" }} />
            <Area type="monotone" dataKey="total" stroke="#00e599" strokeWidth={2} fill="url(#totalG)" />
            <Area type="monotone" dataKey="flagged" stroke="#ff6b6b" strokeWidth={1.5} fill="url(#flagG)" />
            <Area type="monotone" dataKey="blocked" stroke="#f5b544" strokeWidth={1.5} fill="none" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Top users</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>User</th><th>Messages</th></tr></thead>
              <tbody>
                {(usage?.top_users ?? []).map((row) => (
                  <tr key={row.key}>
                    <td>{row.label ?? row.key.slice(0, 10)}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
                {!usage?.top_users.length && <tr><td colSpan={2} className="muted">No data.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2>By AI tool</h2>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={usage?.by_tool ?? []}
                dataKey="count"
                nameKey="key"
                outerRadius={80}
                label={(entry) => entry.key}
              >
                {(usage?.by_tool ?? []).map((entry, index) => (
                  <Cell key={entry.key} fill={TOOL_COLORS[index % TOOL_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Risk categories</h2>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={usage?.by_category ?? []}>
            <CartesianGrid stroke="#1c1d20" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="key" stroke="#3a3d42" tick={{ fill: "#6a6f77" }} fontSize={11} />
            <YAxis stroke="#3a3d42" tick={{ fill: "#6a6f77" }} fontSize={11} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
            <Bar dataKey="count" radius={[5, 5, 0, 0]}>
              {(usage?.by_category ?? []).map((entry) => (
                <Cell key={entry.key} fill={CATEGORY_COLORS[entry.key] ?? "#6a6f77"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          {(usage?.by_category ?? []).map((entry) => (
            <span key={entry.key} className="muted tiny">
              <CategoryBadge category={entry.key as never} /> {entry.count}
            </span>
          ))}
        </div>
      </div>
    </>
  );
}
