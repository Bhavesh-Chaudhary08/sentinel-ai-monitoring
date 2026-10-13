# Sentinel — AI Usage Monitoring & DLP for Managed Work Devices

Visibility into how employees use generative AI (ChatGPT, Gemini, Claude,
Copilot) on company-managed devices, with **content-aware DLP on prompts**:
every outgoing prompt is checked against policy *before* it's sent, risky ones
are flagged/blocked, and admins get real-time alerts and analytics.

> **Consented, transparent by design.** Capture only runs for org-enrolled
> accounts/devices with recorded, versioned consent — the API rejects anything
> else with 403. The employee always sees the state (extension badge, popup,
> dashboard banner) and can view/export their own data. Full prompt text is
> stored **only when flagged**; everything else is a SHA-256 hash plus a
> PII-masked preview. See [docs/consent-model.md](docs/consent-model.md).

> Academic prototype (BTech CSE major project) against a fictional org.
> Not audited for production use — see "Known limitations".

**Want to share it so friends just create an account and go?** See
[DEPLOY.md](DEPLOY.md) — one free VM, auto-HTTPS, and a preconfigured
extension build; nobody else touches a terminal.

---

## Feature map (spec → implementation)

| # | Feature | Where |
|---|---|---|
| 1 | Extension detects AI domains (configurable), captures prompt/response, POSTs with timestamp + user | `extension/src/content/`, `background/service_worker.ts`, domain list in `Settings.known_ai_domains` served via `GET /meta/ai-domains` |
| 2 | Shadow-AI discovery: first-time unrecognized AI domain, risk level | `POST /capture/shadow-visits`, `domain/capture/shadow.py`, extension probe + dynamic script registration, `admin/ShadowAI.tsx` |
| 3 | DLP pipeline: Presidio/spaCy PII + sentence-transformers semantic classes | `domain/classification/` (regex → Presidio → embeddings, graceful fallbacks), findings stored in `classification_finding` |
| 4 | Policy engine: log-only/warn/block per category, role overrides | `domain/policy/engine.py`, CRUD in `api/v1/policy.py`, UI `admin/Policies.tsx` |
| 5 | Celery async alerting → real-time admin dashboard | `workers/tasks.py` → `alert` row → Redis pub/sub → `/api/v1/ws/alerts` → toasts |
| 6 | Admin log: searchable/filterable, analytics, CSV/PDF export | `api/v1/interactions.py`, `analytics/`, `export.py`, `admin/Interactions|Analytics.tsx` |
| 7 | Employee self-view + persistent active indicator | `employee/MyActivity.tsx`, `Layout.tsx` banner, extension popup/badge |
| 8 | RBAC admin/employee via JWT claims | `core/security.py`, `core/deps.py` (`require_admin`, self-scoped queries) |
| 9 | Storage modes: `STORAGE_MODE=full` (default) stores every prompt verbatim and classifies each one; `minimal` retains raw text only for flagged rows (hash + redacted preview otherwise). Configurable retention + hourly purge | `domain/capture/ingest.py`, `domain/capture/minimize.py`, `workers/tasks.py`, hourly `retention.purge_expired_content` sweep |
| 10 | Docker Compose wiring | `docker-compose.yml`: postgres, redis (no persistence), api, worker, beat, migrate, seed, frontend |

## Repository layout

```
├── docker-compose.yml
├── extension/            MV3 capture layer (TS + esbuild)
│   ├── manifest.json  build.mjs  popup/  options/
│   └── src/{background,content,api,rules,shared}/
├── backend/              FastAPI, organized by domain
│   ├── app/{core,db,models,schemas,api,domain,workers}/
│   │   └── domain/{auth,capture,classification,policy,alerts,analytics,audit}/
│   ├── alembic/versions/0001_initial.py
│   └── tests/            pytest (SQLite in-memory, no ML deps needed)
├── frontend/             React + Vite admin & employee dashboards
└── docs/                 architecture · consent-model · threat-model
```

## Quickstart (Docker)

Prereqs: Docker + Docker Compose.

```bash
cp .env.example .env                # then edit SECRET_KEY at minimum
docker compose up -d --build         # first build downloads spaCy/torch (see Lightweight mode to skip)
docker compose --profile tools run --rm seed
open http://localhost:3000          # dashboard  ·  http://localhost:3000/api/docs (proxied)
```

Migrations run automatically (`migrate` service → `alembic upgrade head`).

**Demo accounts** (from `backend/app/db/seed.py`):

| Account | Password | Purpose |
|---|---|---|
| `admin@corp.example` | `Admin@12345` | admin dashboard, policies, alerts |
| `alice@corp.example` | `Employee@123` | employee self-view (Engineering) |
| `bob@corp.example` | `Employee@123` | employee (Finance — see role/department overrides) |
| `temp@corp.example` | `Employee@123` | **not consented** → capture returns 403 (gate demo) |

The seed also installs demo policies: block credentials/confidential, warn
PII/financial, log source code, plus an **admin role override** that downgrades
credential blocks to log-only for incident triage (role-based overrides in action).

### Load the extension

```bash
cd extension && npm install && npm run build
# chrome://extensions → Developer mode → Load unpacked → select extension/dist
```

Then: open the popup → sign in as `alice@corp.example` → read the notice →
**enable monitoring** (this records consent + binds the device). Visit
chatgpt.com/gemini.google.com — the badge turns **ON**; prompts are pre-flighted
and captured.

### Try the DLP end-to-end

1. As alice on chatgpt.com, submit: `Use this key: AKIA1234567890ABCDEF`
   → red **block overlay**, send suppressed (prompt never left the device).
2. Submit something with an email address → amber warning, sent, flagged.
3. As admin: watch the toast appear live (Alerts page), inspect the finding
   (`AWS_ACCESS_KEY`, engine, score), check the redacted preview.
4. Visit some unknown AI-ish site → **Shadow AI** page flags first-seen access
   with a risk rating.
5. Re-run seed/demo tomorrow? Retention sweep + analytics already handle it.

### Lightweight mode (no spaCy/torch)

```bash
INSTALL_NLP=0 INSTALL_ML=0 SEMANTIC_ENABLED=false PRESIDIO_ENABLED=false \
  docker compose up -d --build
```
The classifier then runs regex + lexical similarity only — same code paths,
smaller image, useful on constrained laptops/CI.

## Local development (no Docker)

```bash
# backend (needs a local Postgres or set DATABASE_URL=sqlite:///./dev.db)
cd backend
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head && python -m app.db.seed
uvicorn app.main:app --reload          # http://localhost:8000/api/docs

# tests (no ML deps, in-memory SQLite, classification runs inline)
cd backend && pytest -q

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api)

# extension
cd extension && npm install && npm run build && npm run typecheck
```

`CLASSIFY_SYNC=true` makes ingest classify inline (used by tests; no Redis
needed). Default is async via Celery.

## API surface (prefix `/api/v1`)

| Area | Endpoints |
|---|---|
| auth | `POST /auth/token` · `POST /auth/register` (public, employee-only — admins are created via `POST /users`) · `GET /auth/me` · `POST /auth/consent` |
| meta | `GET /meta/ai-domains` (public — extension bootstrap) |
| capture | `POST /capture/interactions` · `POST /capture/shadow-visits` (consent+device gated) |
| policy | `POST /policy/check` (sync pre-flight) · `GET/POST/PATCH/DELETE /policy/rules` (admin) |
| read | `GET /interactions` (+`/{id}`) · `GET /alerts` (+status POST) · `GET /analytics/usage` · `GET /analytics/shadow-ai` · `GET /audit` · `GET /users` |
| export | `GET /export/interactions?format=csv\|pdf` (self-scoped for employees, audited) |
| realtime | `WS /ws/alerts?token=` (admin) |

Interactive docs: `http://localhost:8000/api/docs`.

## Consent & transparency design decisions

1. **Consent gate in the backend, not the client.** `require_consent` +
   device equality check run server-side; the extension cannot bypass its own
   UI because ignoring it just gets 403s. Consent is stored with a version so
   re-consent after policy changes is provable.
2. **Three independent status surfaces** (badge, popup, dashboard banner) —
   monitoring can't silently run.
3. **Pre-flight over post-hoc only.** Blocking is honest only if it happens
   *before* the prompt leaves the device, so `POST /policy/check` runs inline
   with submit using a fast regex+lexical tier; the heavy pipeline runs async
   afterwards and can still raise/upgrade findings.
4. **Fail open on infrastructure outages** (backend unreachable ⇒ send
   proceeds and capture retries) but **fail closed on policy verdicts**
   (a `block` answer is never overridden client-side).
5. **Minimization is an invariant, not a config flag.** Raw text literally is
   not written at ingest; the worker decides under flagging. Exports and alert
   summaries are built from the masked preview only.
6. **Non-AI browsing generates no records** — the shadow probe only reports
   when chat-UI markers are present, and only domain + booleans + capped title.
7. **Redis has persistence disabled** so the queue can't become a second copy
   of prompt data on disk.
8. **The audit log audits the auditors**: exports, rule edits, alert decisions
   all attribute to an actor.

## Testing

```bash
cd backend && pytest -q
```

Covers: consent gate, device binding, RBAC (403 matrix), idempotent capture,
minimization invariant (benign ⇒ no raw text), flagging ⇒ raw text + alert +
redacted summary, policy specificity/role overrides/priority, quick
pre-flight block, shadow first-seen semantics, classifier tiers + redaction.

Extension/frontend: `npm run typecheck` in each (`npm run build` also
typechecks the frontend).

## Known limitations

- **Selectors drift**: chat UIs redesign often; adapters carry fallbacks but
  need periodic updates (inherent to extension capture).
- Pre-flight **blocking requires form-based submit**; Enter-only composers get
  post-hoc classification + capture, but not send-blocking (noted in code).
- Demo auth: JWT in `localStorage` (dashboard) / `chrome.storage` (extension);
  production should use HttpOnly cookies + tighter device binding.
- Lexical tier can over/under-fire on niche phrasing; thresholds are config,
  and `false_positive` alert workflow exists for correction loops.
- Analytics aggregate in Python (fine to ~10⁶ rows); SQL/materialized views
  beyond that.
- Loss of queued Redis messages during prolonged outages is surfaced (stale
  `pending` → `failed`) rather than silently hidden.

## Roadmap / future work

- [ ] Self-service "why was this flagged?" + appeal flow for employees
- [ ] yara-like org term lists per department; external domain reputation feed
- [ ] KMS encryption for flagged content at rest; WORM audit export
- [ ] Extension: MV3 offscreen doc for heavier DOM work; Firefox port
- [ ] Enforcement modes beyond pre-flight (network proxy re-check)

## Docs

- [docs/architecture.md](docs/architecture.md) — components, two data flows,
  schema, tiering, resolution order
- [docs/consent-model.md](docs/consent-model.md) — consent lifecycle, what is
  (not) collected, employee rights
- [docs/threat-model.md](docs/threat-model.md) — assets, STRIDE-lite table,
  residual risks, hardening path
