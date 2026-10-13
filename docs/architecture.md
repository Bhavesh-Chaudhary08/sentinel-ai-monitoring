# Architecture

## System components

```
┌─────────────────────────── Browser (enrolled device) ───────────────────────────┐
│  MV3 Extension                                                                   │
│  ├─ content script  ─ conversation observer + DLP pre-flight hook + overlay      │
│  ├─ background SW   ─ durable queue · batched flush · auth · shadow probe        │
│  └─ popup/options   ─ consent flow + always-visible monitoring indicator         │
└───────────────┬──────────────────────────────────────────────────────────────────┘
                │ HTTPS (Bearer JWT)
┌───────────────▼──────────────── FastAPI (async) ────────────────────────────────┐
│  api/v1: auth · capture · policy · interactions · alerts · analytics · export   │
│  domain/: auth · capture(minimize,shadow,ingest) · classification · policy      │
│           alerts(dispatcher,realtime) · analytics · audit                       │
└──────┬───────────────────────────────┬──────────────────────────┬───────────────┘
       │                               │                          │
┌──────▼──────┐                 ┌──────▼──────┐            ┌──────▼──────┐
│ PostgreSQL  │                 │    Redis    │            │   Celery    │
│ (SQLModel + │                 │ queue + pub │◄───────────┤ worker/beat │
 │  Alembic)  │                 │  (no disk)  │  classify  │ classify ·  │
└──────▲──────┘                 └──────▲──────┘  alert     │ alert ·     │
       │                               │  pub/sub           │ retention   │
       └───────────┬───────────────────┘                    └─────────────┘
                   │
        ┌──────────▼──────────┐     ┌──────────────────────────────┐
        │  React dashboard    │────►│  nginx (same origin: static  │
        │  admin + employee   │ WS  │  + /api proxy incl. upgrade) │
        └─────────────────────┘     └──────────────────────────────┘
```

## Two data flows (deliberate split)

### 1. Pre-flight (synchronous, inline with the send)

```
composer submit ──► content script cancels send
                 ──► POST /policy/check  {prompt, tool, domain}
                 ──► quick classifier: regex tier + lexical similarity
                 ──► policy engine      : rule resolution (role overrides)
                 ◄── {action: block|warn|log_only, message}
   block  → overlay shown, send never happens (prompt never leaves the device)
   warn   → overlay shown, send proceeds, everything logged
   allow  → send proceeds silently
```

Why quick-only here: the request path must never load spaCy/torch. The quick
tier is pure-Python regex + keyword/overlap scoring — deterministic, <10ms.

### 2. Capture + full classification (asynchronous)

```
observer sees new message ──► background queue (chrome.storage.session)
                            ──► batched POST /capture/interactions
                                gates: JWT → active user → consent → device match
ingest: sha256(prompt), PII-masked preview, metadata row (raw text NOT stored)
                            ──► Celery task with raw text as argument
worker: full pipeline (regex → Presidio/spaCy → sentence-transformers)
        ├─ not flagged  → raw text dropped (hash + preview only)
        ├─ flagged      → raw text retained, purge_after = now + retention
        ├─ policy engine → applied_action + rule link
        └─ warn/block    → Alert row → send_alert task → Redis pub/sub
                                             ──► WS relay ──► admin dashboard toast
```

Redis runs with **AOF and RDB disabled**: the broker never writes prompt text
to disk; queue messages exist only in memory until consumed.

## Database schema (6 tables)

| Table | Purpose |
|---|---|
| `user` | accounts, RBAC role, **consent + device enrollment** record |
| `captured_interaction` | one row per captured message/visit: metadata, hash, preview, classification outcome, policy outcome, retention fields |
| `classification_finding` | 1:N per-interaction detections (`engine`, `label`, `score`, offsets) — shows *why* something flagged |
| `policy_rule` | matchers (category/tool/domain/confidence) + scope (role/department) + action + messages |
| `alert` | one per high-confidence violation; severity, status workflow, redacted summary |
| `audit_log` | append-only privileged-action trail (rule CRUD, exports, alert decisions, account lifecycle) |

Enum columns are native Postgres enums — SQLModel ≥0.0.9 maps `(str, Enum)`
that way, and `0001_initial.py` mirrors it exactly.

Notable constraints: unique `(user_id, client_event_id)` for idempotent
extension retries; composite indexes for the hot filters
(user+time, category+time, domain+known).

## Classification pipeline (three tiers)

| Tier | Engine | Used in | Latency |
|---|---|---|---|
| 1 | regex patterns (AWS keys, tokens, private keys, SSN, Luhn cards, IBAN, emails…) | pre-flight **and** full | µs |
| 2 | Microsoft Presidio + spaCy NER (named PII entities) | full only | ~10–50ms |
| 3 | sentence-transformers (`all-MiniLM-L6-v2`) cosine similarity vs reference corpus | full only | ~5–20ms (after load) |

- Pre-flight = tier 1 + a lexical scorer (keyword coverage + token overlap over
  the same reference corpus) — the corpus is shared, so pre-flight decisions
  correlate well with the async verdict.
- Scores per category are merged by max; ties break by precedence
  credentials > financial > pii > confidential > source_code.
- `is_flagged = category != none && score >= flag_threshold (0.50)`.
- Every tier degrades gracefully: missing Presidio/spaCy/torch ⇒ logged warning
  and automatic fallback, never a failed capture.

## Policy resolution order

1. rule active **and** matches every non-null matcher (category, tool, domain,
   `min_confidence <= score`, role scope, department scope)
2. specificity: role/department-scoped rules beat global ones
3. `priority` desc, then `min_confidence` desc
4. no match ⇒ `log_only` (capture itself is unconditional)

Rules are **deactivated, never deleted** — `alert.rule_id` and
`captured_interaction.policy_rule_id` are long-lived FK references.

## Shadow-AI discovery

1. `webNavigation.onCompleted` on a host **not** in `KNOWN_AI_DOMAINS`
   (served from `GET /meta/ai-domains`, extendable via env/JSON — one source
   of truth shared with the extension) and only while consented+enrolled
2. tiny probe injected: `{composer, send_label, chat_words}` booleans + title
   only — **no page content leaves the device**
3. `POST /capture/shadow-visits` → backend flags **first-seen** access per
   (user, domain) and risk-rates it (impersonation/disposable TLD → high …)
4. response tells the extension which domains may now register the generic
   capture adapter dynamically (`chrome.scripting.registerContentScripts`)

## Alerting

- Created only for `warn`/`block` outcomes (`warn` additionally needs
  `score >= alert_min_score`) — confidence gate keeps noise down.
- Severity: block → high (critical ≥0.95), warn → medium.
- Fan-out: worker task → `Alert` row (committed first) → Redis pub/sub →
  per-connection WS relay in the API → toast. DB is source of truth; a dropped
  socket just means the UI refetches.

## Retention / data minimization mechanics

Two storage modes via `STORAGE_MODE`:
- `full` (default): ingest stores every prompt/response verbatim, `purge_after =
  now + RETENTION_DAYS_FULL` (flagged rows later upgrade to the flagged window).
  Every prompt is still classified — safe and risky alike get a verdict.
- `minimal`: ingest never writes raw text; the worker retains it only for
  flagged rows with `purge_after = now + RETENTION_DAYS_FLAGGED`. Everything
  else is a sha256 hash + redacted preview.

- hourly Celery beat sweep nulls expired content, metadata rows survive for
  audit/analytics
- rows stuck `pending` >15min are marked `failed` (broker loss visibility)
- a classification below `flag_threshold` reports `category=none` (score kept)
  so weak sub-threshold matches never pollute per-category analytics

## Scaling notes (beyond the prototype)

- worker concurrency and API statelessness are the easy axes; classification
  model is the memory hog (load one per worker process)
- extract classification to a dedicated queue/Deployment when volume grows
- move analytics aggregation to materialized views past ~10⁶ rows
