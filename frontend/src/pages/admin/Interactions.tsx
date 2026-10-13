import { useCallback, useEffect, useState } from "react";
import { api, downloadFile, exportPath, type Interaction, type Page } from "../../api/client";
import { InteractionDetailModal, InteractionTable } from "../../components/InteractionTable";

const CATEGORIES = ["", "pii", "source_code", "financial", "confidential", "credentials", "none"];
const TOOLS = ["", "chatgpt", "gemini", "claude", "copilot", "other"];
const PAGE_SIZE = 25;

export default function Interactions() {
  const [data, setData] = useState<Page<Interaction> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);

  // Filter state + a "draft" layer so selects don't refetch on every keystroke.
  const [filters, setFilters] = useState({
    q: "",
    category: "",
    tool: "",
    flagged: "",
    shadowOnly: false,
    from: "",
    to: "",
  });
  const [draft, setDraft] = useState(filters);

  const load = useCallback(async () => {
    try {
      const result = await api.interactions({
        page,
        page_size: PAGE_SIZE,
        q: filters.q || undefined,
        category: filters.category || undefined,
        tool: filters.tool || undefined,
        flagged: filters.flagged === "flagged" ? true : filters.flagged === "clean" ? false : undefined,
        shadow_only: filters.shadowOnly || undefined,
        from: filters.from ? `${filters.from}T00:00:00` : undefined,
        to: filters.to ? `${filters.to}T23:59:59` : undefined,
      });
      setData(result);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [page, filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <h1>Interaction log</h1>
      <p className="page-sub">
        Searchable, filterable record of every captured prompt/response — flagged rows show
        raw text, the rest keep hash + masked preview only.
      </p>

      <div className="card">
        <div className="filters">
          <div className="field grow">
            <label htmlFor="q">Domain search</label>
            <input
              id="q"
              placeholder="chatgpt.com…"
              value={draft.q}
              onChange={(e) => setDraft({ ...draft, q: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="cat">Category</label>
            <select id="cat" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c || "all"}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tool">AI tool</label>
            <select id="tool" value={draft.tool} onChange={(e) => setDraft({ ...draft, tool: e.target.value })}>
              {TOOLS.map((t) => <option key={t} value={t}>{t || "all"}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="flag">Flagging</label>
            <select id="flag" value={draft.flagged} onChange={(e) => setDraft({ ...draft, flagged: e.target.value })}>
              <option value="">all</option>
              <option value="flagged">flagged only</option>
              <option value="clean">not flagged</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="from">From</label>
            <input id="from" type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="to">To</label>
            <input id="to" type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="shadow">Shadow AI</label>
            <select
              id="shadow"
              value={draft.shadowOnly ? "only" : "all"}
              onChange={(e) => setDraft({ ...draft, shadowOnly: e.target.value === "only" })}
            >
              <option value="all">all domains</option>
              <option value="only">unrecognized only</option>
            </select>
          </div>
          <div className="field">
            <button
              className="primary"
              onClick={() => {
                setFilters(draft);
                setPage(1);
              }}
            >
              Apply
            </button>
          </div>
        </div>

        <div className="form-actions">
          <button className="small ghost" onClick={() => void downloadFile(exportPath("csv", currentParams()), "interactions.csv")}>
            Export CSV
          </button>
          <button className="small ghost" onClick={() => void downloadFile(exportPath("pdf", currentParams()), "interactions.pdf")}>
            Export PDF
          </button>
          <span className="muted tiny">
            Exports respect your current filters and are recorded in the audit log.
          </span>
        </div>

        {error && <p className="error">{error}</p>}

        <div style={{ marginTop: 14 }}>
          <InteractionTable items={data?.items ?? []} onSelect={(i) => setSelected(i.id)} />
        </div>

        <div className="pagination">
          <span>
            {data ? `${data.total} rows · page ${data.page} / ${totalPages}` : "loading…"}
          </span>
          <div className="buttons">
            <button className="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              ← Prev
            </button>
            <button className="small" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
              Next →
            </button>
          </div>
        </div>
      </div>

      {selected && (
        <InteractionDetailModal interactionId={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );

  function currentParams() {
    return {
      q: filters.q || undefined,
      category: filters.category || undefined,
      tool: filters.tool || undefined,
      flagged: filters.flagged === "flagged" ? true : filters.flagged === "clean" ? false : undefined,
      shadow_only: filters.shadowOnly || undefined,
      from: filters.from ? `${filters.from}T00:00:00` : undefined,
      to: filters.to ? `${filters.to}T23:59:59` : undefined,
    };
  }
}
