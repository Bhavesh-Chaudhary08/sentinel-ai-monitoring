"""Pipeline: regex tier → (optional) Presidio → (optional) embeddings.

Two entry points:
- classify_prompt(..., quick=True): synchronous pre-flight used by /policy/check.
  Regex + lexical only, so it never loads spaCy or torch on the request path.
- classify_prompt(...): full async classification run by the Celery worker.
"""

from dataclasses import dataclass, field

from app.core.config import settings
from app.core.enums import RiskCategory
from app.domain.classification import patterns
from app.domain.classification.presidio_engine import engine as presidio
from app.domain.classification.registry import SEMANTIC_CATEGORIES, lexical_scores
from app.domain.classification.semantic_engine import semantic_scores

# Tie-break order when two categories score identically: secrets beat money
# beat identity data, generic last.
_CATEGORY_PRECEDENCE = [
    RiskCategory.credentials,
    RiskCategory.financial,
    RiskCategory.pii,
    RiskCategory.confidential,
    RiskCategory.source_code,
    RiskCategory.other,
]


@dataclass
class Detection:
    engine: str  # regex | presidio | semantic | lexical
    label: str
    category: RiskCategory
    score: float
    start: int | None = None
    end: int | None = None


@dataclass
class ClassificationResult:
    category: RiskCategory
    score: float
    detections: list[Detection] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return self.category != RiskCategory.none and self.score >= settings.flag_threshold

    @property
    def version(self) -> str:
        return "+".join(self.engines) if self.engines else "empty"


def _precedence_key(category: RiskCategory) -> int:
    try:
        return _CATEGORY_PRECEDENCE.index(category)
    except ValueError:
        return len(_CATEGORY_PRECEDENCE)


def classify_prompt(text: str, *, quick: bool = False) -> ClassificationResult:
    text = (text or "").strip()
    if not text:
        return ClassificationResult(RiskCategory.none, 0.0, [], ["empty"])

    detections: list[Detection] = []
    engines: list[str] = ["regex"]

    for label, category, score, start, end in patterns.find_detections(text):
        detections.append(Detection("regex", label, category, score, start, end))

    if not quick:
        for label, category, score, start, end in presidio.analyze(text):
            detections.append(Detection("presidio", label, category, score, start, end))
        if presidio.available:
            engines.append("presidio")

    # --- category score aggregation (max per category) ---
    cat_scores: dict[RiskCategory, float] = {}
    for det in detections:
        if det.category != RiskCategory.none:
            cat_scores[det.category] = max(cat_scores.get(det.category, 0.0), det.score)

    if quick:
        similarity = lexical_scores(text)
        engines.append("lexical")
    else:
        similarity = semantic_scores(text)
        engines.append("semantic" if settings.semantic_enabled else "lexical")

    for category, score in similarity.items():
        cat_scores[category] = max(cat_scores.get(category, 0.0), score)

    if not cat_scores:
        return ClassificationResult(RiskCategory.none, 0.0, detections, engines)

    best_category = max(
        cat_scores,
        key=lambda c: (round(cat_scores[c], 4), -_precedence_key(c)),
    )
    best_score = round(cat_scores[best_category], 4)
    if best_score < settings.flag_threshold:
        # Below the flag threshold nothing "sticks": the text is reported as
        # safe (category=none) so weak lexical/semantic matches don't pollute
        # per-category analytics. The score is still surfaced for transparency.
        return ClassificationResult(RiskCategory.none, best_score, detections, engines)
    return ClassificationResult(best_category, best_score, detections, engines)
