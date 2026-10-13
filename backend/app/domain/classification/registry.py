"""Reference corpus + lexical similarity scorer.

The lexical scorer is the dependency-free fallback for the semantic tier: it is
used for the synchronous pre-flight policy check (no model load in the hot
path) and whenever sentence-transformers is not installed (lightweight mode).
"""

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app.core.enums import RiskCategory

# Lives next to this module (no `registry/` directory — it would shadow this file).
_DATA_FILE = Path(__file__).parent / "reference_examples.json"

TOKEN_RE = re.compile(r"[a-z_][a-z0-9_]*|\d+")

# Categories the similarity engines score (PII is handled by regex/Presidio).
SEMANTIC_CATEGORIES: list[RiskCategory] = [
    RiskCategory.source_code,
    RiskCategory.financial,
    RiskCategory.confidential,
    RiskCategory.credentials,
]


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@lru_cache(maxsize=1)
def reference_examples() -> dict[str, dict]:
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return {cat: {"keywords": spec["keywords"], "examples": spec["examples"]} for cat, spec in raw.items()}


@lru_cache(maxsize=1)
def _example_token_sets() -> dict[str, Counter]:
    out: dict[str, Counter] = {}
    for cat, spec in reference_examples().items():
        counter: Counter = Counter()
        for example in spec["examples"]:
            counter.update(tokenize(example))
        out[cat] = counter
    return out


def lexical_scores(text: str) -> dict[RiskCategory, float]:
    """Keyword-coverage + token-overlap similarity in [0, 1] per category."""
    lowered = text.lower()
    tokens = Counter(tokenize(text))
    example_sets = _example_token_sets()
    scores: dict[RiskCategory, float] = {}

    for cat, spec in reference_examples().items():
        keywords = spec["keywords"]
        hits = sum(1 for kw in keywords if kw.lower().strip() in lowered)
        keyword_ratio = hits / len(keywords) if keywords else 0.0

        ex_counter = example_sets.get(cat, Counter())
        if ex_counter:
            # Weight distinctive example tokens higher than stopwords-like ones.
            overlap = sum(min(count, tokens.get(tok, 0)) for tok, count in ex_counter.items())
            union = sum(ex_counter.values()) + sum(
                count for tok, count in tokens.items() if tok not in ex_counter
            )
            jaccard = overlap / union if union else 0.0
        else:
            jaccard = 0.0

        # A handful of keyword hits OR strong example overlap should reach the
        # ~0.45 threshold; a lone incidental word should not.
        raw = max(2.5 * keyword_ratio, 2.0 * jaccard)
        scores[cat] = round(min(1.0, raw), 4)

    return scores
