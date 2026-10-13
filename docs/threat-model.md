# Threat Model (prototype scope)

STRIDE-lite over the docker-compose deployment.

## Assets

1. **Prompt/response content** — may contain secrets, PII, client data, source
   code (the whole reason DLP exists)
2. **Policy definitions** — an attacker who edits rules disables enforcement
3. **Audit trail integrity** — if mutable, accountability collapses
4. **JWT signing key (`SECRET_KEY`)** — possession = any identity
5. **Employee reputation** — false flags have real consequences

## Trust boundaries

1. Employee-controlled browser ↔ extension (content scripts read the page DOM;
   page content is untrusted input)
2. Extension ↔ API (corp LAN/TLS assumed in production)
3. API ↔ Redis/Postgres (compose-internal network)
4. Admin users ↔ dashboard (role elevation path)
5. Celery worker ↔ model files (Hugging Face corpus — supply-chain surface)

## Threats & mitigations

| # | Threat | STRIDE | Mitigation in this codebase | Residual |
|---|---|---|---|---|
| 1 | Forged/replayed capture events | Spoofing | JWT required; `device_id` must equal enrollment; unique `(user_id, client_event_id)` makes replays idempotent no-ops | Stolen token+device id from the same machine ≈ full impersonation (short TTL helps) |
| 2 | Employee uninstalls/disables extension | Repudiation | Disabling is visible (admin sees enrollment state, stale data); honest-tool threat model accepts user-visible opt-out rather than enforcing spyware behavior | accepted — transparency beats coercion by design |
| 3 | Prompt text written to disk by the broker | Info disclosure | Redis runs `--appendonly no --save ""`; raw text exists in a queue message only until consumed | in-flight messages readable with broker access (internal network) |
| 4 | Unflagged content retained | Info disclosure | Storage-mode dependent: `full` stores everything verbatim (accepted trade-off, short `retention_days_full` + hourly purge); `minimal` writes raw text only when `flagged && store_raw_when_flagged`; ingest always writes hash+preview; hourly purge enforces `purge_after` | test `test_benign_prompt_verdict_depends_on_storage_mode` + `test_minimal_mode_still_drops_benign_text` lock both invariants |
| 5 | Leaking raw text via alerts/reports | Info disclosure | Alert summary and CSV/PDF are built from `redacted_preview`; redaction = regex spans + Presidio spans, masked before storage | redactor misses exotic PII formats |
| 6 | Employee reads other users' data | Elevation | `apply_filters` forces `user_id = self` for non-admins; detail endpoint returns 404 (not 403) for foreign IDs; admin-only routers guarded by `require_admin` | — |
| 7 | Rule tampering disables blocking | Tampering | Rule CRUD admin-only + JWT role claim; every mutation audit-logged with actor and field list; rules deactivate (soft) so history can't be rewritten | DBA can still edit rows directly (see #9) |
| 8 | Forged JWT / alg confusion | Spoofing | `python-jose` decode with fixed HS256 + `iss` check; `decode_token` rejects anything malformed | weak `SECRET_KEY` in dev (compose warns) |
| 9 | Admin abuses the monitor | Repudiation | Append-only `audit_log` for privileged actions; employee self-view means retention is inspectable by the subject; README documents policy ownership | DBA-level actors outside the app (monitor the DB too, in production) |
| 10 | Content script runs in hostile page | Tampering/XSS | Content script never trusts page text: it only ships text as opaque capture payloads (JSON, length-capped); alert summaries are HTML-escaped in the overlay; dashboard renders React text nodes | malicious page could feed junk data (integrity noise, not a security breach) |
| 11 | Queue loss = silent DLP blind spot | DoS | `task_acks_late`; stale-`pending` sweep marks orphaned rows `failed` every 10min so gaps are visible | events still queued during prolonged outage are dropped after cap (500) |
| 12 | Model supply chain (HF weights) | Tampering | Pinned versions; models referenced by name; fallback tiers mean a poisoned/absent model degrades to regex/lexical | first-download trust in Hugging Face |
| 13 | Shadow probe over-collecting | Info disclosure | Probe sends domain + 3 booleans + truncated title; runs only when consented+enrolled; marker threshold decides before any reporting | title could contain user-typed text on odd sites (120-char cap) |
| 14 | Insider crafting lookalike domains | Evasion | Risk heuristic: brand terms in unrecognized hosts → high; disposable TLDs → high; report is per-user attributable | heuristic, not a reputation feed (future: blocklist integration) |

## Deliberate non-goals

- hiding from the monitored user (any feature that would do so is rejected)
- kernel/endpoint agents, screenshots, keystroke capture
- blocking by rewriting third-party sites beyond form-submit interception
- legal compliance certification (this is an academic prototype)

## Highest-priority hardening for a real deployment

1. TLS everywhere + `SECRET_KEY` from a real KMS; rotate + short-lived tokens
2. HttpOnly/SameSite cookie session for the dashboard (localStorage JWT is a
   demo tradeoff) and DPoP-style token-device binding for the extension
3. Encrypt flagged content at rest (KMS envelope) + column-level encryption
   for `prompt_text`
4. DB-level append-only rules / WORM export for `audit_log`
5. Rate limiting + anomaly alerts on capture volume per device
6. External domain reputation feed for shadow-AI risk ratings
