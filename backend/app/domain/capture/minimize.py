"""Data-minimization primitives: hashing, truncation, preview redaction.

Contract (see CapturedInteraction docstring):
- prompt_hash  = sha256(prompt) — ALWAYS, enables dedupe/audit without content
- redacted_preview = PII/secret-masked prefix — ALWAYS safe to display
- raw prompt/response text — only ever persisted by the worker when flagged
"""

import hashlib

from app.core.config import settings
from app.domain.classification.patterns import DETECTION_PATTERNS

REDACTED = "[REDACTED]"


def is_full_storage() -> bool:
    """True ⇒ capture mode stores every prompt verbatim (not just flagged ones)."""
    return settings.storage_mode.lower() == "full"


def sha256_text(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate(text: str | None, limit: int) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return text[:limit] + "\n…[truncated]"


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def collect_redaction_spans(text: str) -> list[tuple[int, int]]:
    """Regex spans + Presidio entity spans (Presidio optional, lazy)."""
    spans = [
        (m.start(), m.end())
        for pat in DETECTION_PATTERNS
        for m in pat.regex.finditer(text)
    ]
    try:
        from app.domain.classification.presidio_engine import engine as presidio

        spans.extend((start, end) for _, _, _, start, end in presidio.analyze(text))
    except Exception:  # never let redaction blow up ingest
        pass
    return _merge_spans(spans)


def redact_text(text: str) -> str:
    """Mask every PII/secret span with [REDACTED]; deterministic and local."""
    if not text:
        return text
    spans = collect_redaction_spans(text)
    if not spans:
        return text
    out: list[str] = []
    cursor = 0
    for start, end in spans:
        out.append(text[cursor:start])
        out.append(REDACTED)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def build_preview(text: str | None) -> str | None:
    """Short, masked, always-store-safe preview of a prompt."""
    if not text:
        return None
    return truncate(redact_text(text), settings.redacted_preview_chars)
