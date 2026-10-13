"""Regex detection tier — zero dependencies, sub-millisecond, always available.

Serves two purposes:
1. detection findings fed into the classifier,
2. redaction spans used to scrub previews (see capture/minimize.py).

Score values are deliberately conservative: strong secrets/IDs score high,
generic identifiers score medium so a single email doesn't outrank an AWS key.
"""

import re
from dataclasses import dataclass

from app.core.enums import RiskCategory


@dataclass(frozen=True)
class RegexPattern:
    label: str
    category: RiskCategory
    score: float
    regex: re.Pattern


def _luhn_valid(candidate: str) -> bool:
    digits = [int(c) for c in re.sub(r"[^\d]", "", candidate)]
    if not 13 <= len(digits) <= 16:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

DETECTION_PATTERNS: list[RegexPattern] = [
    # --- credentials / secrets (highest DLP priority) ---
    RegexPattern("PRIVATE_KEY_BLOCK", RiskCategory.credentials, 0.99,
                 re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    RegexPattern("AWS_ACCESS_KEY", RiskCategory.credentials, 0.97,
                 re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    RegexPattern("GITHUB_TOKEN", RiskCategory.credentials, 0.95,
                 re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    RegexPattern("SLACK_TOKEN", RiskCategory.credentials, 0.95,
                 re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    RegexPattern("GENERIC_SECRET_ASSIGNMENT", RiskCategory.credentials, 0.85,
                 re.compile(r"\b(?:api[_-]?key|secret|passwd|password|access[_-]?token)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-/+.]{12,}",
                            re.IGNORECASE)),
    # --- PII ---
    RegexPattern("SSN", RiskCategory.pii, 0.92, re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    RegexPattern("EMAIL", RiskCategory.pii, 0.65,
                 re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    RegexPattern("PHONE", RiskCategory.pii, 0.60,
                 re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    # --- financial ---
    RegexPattern("IBAN", RiskCategory.financial, 0.88,
                 re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    # CREDIT_CARD is validated with the Luhn checksum in find_detections().
    RegexPattern("CREDIT_CARD", RiskCategory.financial, 0.90, CREDIT_CARD_RE),
    # --- source code smells (weak signals on their own; semantics dominate) ---
    RegexPattern("CODE_BLOCK", RiskCategory.source_code, 0.55,
                 re.compile(r"\b(?:def \w+\s*\(|function \w+\s*\(|import \w+|public class|console\.log|SELECT .* FROM .+)\b",
                            re.IGNORECASE | re.DOTALL)),
]


def find_detections(text: str) -> list[tuple[str, RiskCategory, float, int, int]]:
    """Return (label, category, score, start, end) tuples for every regex hit."""
    out: list[tuple[str, RiskCategory, float, int, int]] = []
    for pat in DETECTION_PATTERNS:
        for match in pat.regex.finditer(text):
            if pat.label == "CREDIT_CARD" and not _luhn_valid(match.group(0)):
                continue
            out.append((pat.label, pat.category, pat.score, match.start(), match.end()))
    return out
