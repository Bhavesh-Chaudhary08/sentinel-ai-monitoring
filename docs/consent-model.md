# Consent & Transparency Model

This tool is a **consented, transparent monitor**, not surveillance software.
That framing is an architectural commitment, not a disclaimer — several
mechanics exist only to enforce it.

## Design principles

1. **Consent precedes capture.** The API rejects every capture request unless
   the target user has `consent_accepted=true` AND `is_enrolled=true` AND the
   payload `device_id` matches the enrolled device. A valid JWT alone is not
   enough; consent is recorded with a **policy version + timestamp** so the
   trail proves *which* notice text was accepted.
2. **The employee always sees the state.** Three independent surfaces:
   extension badge ("ON" on AI sites), extension popup (status + notice text),
   dashboard banner ("Monitoring ON/off" on every page of the self-view).
   Monitoring can't quietly run in the background.
3. **Notice before content.** The popup's consent screen enumerates exactly
   what is collected before anything is enabled — no blanket click-through.
4. **The monitored person sees their own data.** `/me` mirrors the admin's log
   for their own rows, including the exact stored text (flagged rows only),
   classification findings, rule that fired, and a self-export button.
5. **Least content retained.** See table below; retention windows are config,
   not code, and enforced by an automated sweep.

## What is collected

| Data | When | Why |
|---|---|---|
| SHA-256 of prompt | always (prompt events) | dedupe/audit without content |
| PII-masked preview (≤400 chars) | always (prompt events) | display + alert summaries without raw text |
| Metadata (user, tool, domain, path, timestamps, outcome) | always | usage analytics, shadow-AI discovery |
| **Full prompt/response text** | **only if flagged** | evidence for the violation + reviewer context |
| Domain + boolean UI markers (probe) | first-seen unknown AI sites only | shadow-AI discovery — never page content |
| Never collected | keystrokes before submit, unflagged full text, browsing history, screenshots, non-AI sites (beyond the marker probe) | — |

## Consent lifecycle

```
admin creates account
   → employee opens extension popup → signs in with org account
   → popup shows the notice (version = settings.consent_version)
   → employee accepts → POST /auth/consent {device_id, extension_version}
   → user.is_enrolled = true, consent_at/version recorded
   → capture requests now pass the gate

employee signs out of the extension / admin disables account
   → capture stops at the same gate; queued events are NOT flushed
   → dynamic content scripts are unregistered

device change (reinstall)
   → device_id mismatch ⇒ 403 with "re-confirm consent" ⇒ re-enrollment
```

## Enforcement surfaces (where the promise is kept)

- **Backend**: `require_consent` dependency + device equality check on both
  capture endpoints; RBAC scoping so employees can *only* read their own rows.
- **Extension**: probes and capture only run while `consent_accepted &&
  is_enrolled`; unenrolled profiles generate zero network traffic from the
  extension.
- **Worker**: raw text written only under the flagging decision; purge job
  enforces the window afterwards.
- **Alerts/exports**: summaries and reports are built from the redacted
  preview — raw text never enters the alerting path or CSV/PDF exports.
- **Audit log**: every admin read-path with side effects (exports), rule
  change, and alert decision is attributable to an actor.

## Employee rights exercised in-product

- view own logged activity + flagged evidence (self-view page)
- export own data as CSV (same `/export` endpoint, auto-scoped to self)
- see consent version/date and monitoring state anywhere in the dashboard
- raise `false_positive` on an alert via the admin queue (workflow exists for
  delegated review; a self-service variant is listed as future work)

## What this project deliberately does NOT do

- no keylogging or capture before the user submits to an AI tool
- no covert mode: there is no setting that hides monitoring from the employee
- no capture on accounts/devices outside the enrolled set
- no full-text retention of benign activity (hash + preview only)
- no cross-user browsing profiles: non-AI navigations leave no record beyond
  the in-browser probe decision
