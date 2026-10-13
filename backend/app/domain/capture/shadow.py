"""Shadow-AI discovery: known-platform check + first-seen risk heuristic.

`known_ai_domains` lives in Settings so ops can extend it via the
KNOWN_AI_DOMAINS env var (JSON array) — the extension fetches the same list
from GET /api/v1/meta/ai-domains, keeping one source of truth.
"""

import re

from app.core.config import settings
from app.core.enums import ShadowRisk

# Brand terms that, appearing in an *unrecognized* host, smell like impersonation.
_IMPERSONATION_TERMS = (
    "chatgpt", "openai", "claude", "anthropic", "gemini", "copilot",
    "midjourney", "perplexity", "bard",
)
_SUSPICIOUS_TLDS = {"xyz", "top", "click", "work", "gq", "tk", "ml", "cf", "zip", "mov"}
_AI_MARKER_WORDS = ("chat", "assistant", "gpt", "genai", "llm", "bot", "ai-")

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def normalize_domain(raw: str) -> str:
    """Lowercase, strip scheme/path/port/www — as sent by the extension."""
    value = (raw or "").strip().lower()
    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
    if value.startswith("www."):
        value = value[4:]
    return value[:255]


def is_known_platform(domain: str) -> bool:
    domain = normalize_domain(domain)
    for known in settings.known_ai_domains:
        known = known.lower()
        if domain == known or domain.endswith("." + known):
            return True
    return False


def is_valid_domain(domain: str) -> bool:
    return bool(_DOMAIN_RE.match(domain))


def assess_shadow_risk(
    domain: str,
    markers: dict[str, bool] | None = None,
    page_title: str | None = None,
) -> ShadowRisk:
    """Cheap, explainable heuristic. Documented in docs/threat-model.md."""
    domain = normalize_domain(domain)
    if not domain:
        return ShadowRisk.unknown

    labels = domain.split(".")
    tld = labels[-1]
    stem = ".".join(labels[:-1])

    # 1. Brand term in an unrecognized host → likely impersonation.
    if any(term in stem for term in _IMPERSONATION_TERMS):
        return ShadowRisk.high
    # 2. Cheap/disposable TLD commonly used for phishing kits.
    if tld in _SUSPICIOUS_TLDS:
        return ShadowRisk.high
    # 3. Probe found a real chat composer + send affordance.
    markers = markers or {}
    if markers.get("composer") and markers.get("send_label"):
        return ShadowRisk.medium
    # 4. AI-ish naming.
    if any(word in stem for word in _AI_MARKER_WORDS):
        return ShadowRisk.medium
    # 5. Title hints at chat UI (title only — no page content is ever sent).
    if page_title and re.search(r"\b(chat|assistant|ai)\b", page_title, re.IGNORECASE):
        return ShadowRisk.medium
    return ShadowRisk.low
