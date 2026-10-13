"""Presidio + spaCy tier: named PII entity detection.

Everything here is lazy and failure-tolerant — missing packages or a missing
spaCy model downgrade the pipeline to the regex tier instead of crashing.
"""

import logging

from app.core.config import settings
from app.core.enums import RiskCategory

logger = logging.getLogger("aidlp.classification.presidio")

# Entities that are money-data rather than person-data.
FINANCIAL_ENTITIES = {
    "CREDIT_CARD",
    "IBAN",
    "US_BANK_NUMBER",
    "US_BANK_ROUTING",
    "US_ADTL_TAXID",
}


class PresidioEngine:
    def __init__(self) -> None:
        self._analyzer = None
        self._initialised = False
        self.available = False
        self.last_error: str | None = None

    def _ensure(self) -> None:
        if self._initialised:
            return
        self._initialised = True
        if not settings.presidio_enabled:
            self.last_error = "disabled by PRESIDIO_ENABLED=false"
            return
        try:
            from presidio_analyzer import AnalyzerEngine, NlpEngineProvider

            provider = NlpEngineProvider(
                nlp_configuration={"lang": "en", "model_name": settings.spacy_model}
            )
            nlp_engine = provider.create_engine()
            self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self.available = True
            logger.info("Presidio ready (spaCy model: %s)", settings.spacy_model)
        except Exception as exc:  # missing package, missing model, CPU limits...
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Presidio unavailable, falling back to regex tier (%s)", self.last_error)

    def analyze(self, text: str) -> list[tuple[str, RiskCategory, float, int, int]]:
        """Return (entity_type, category, score, start, end) detections."""
        self._ensure()
        if not self._analyzer or not text:
            return []
        try:
            results = self._analyzer.analyze(text=text, language="en")
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Presidio analyze failed: %s", self.last_error)
            return []
        out: list[tuple[str, RiskCategory, float, int, int]] = []
        for r in results:
            if r.score < 0.5:
                continue
            category = RiskCategory.financial if r.entity_type in FINANCIAL_ENTITIES else RiskCategory.pii
            out.append((r.entity_type, category, float(r.score), r.start, r.end))
        return out


engine = PresidioEngine()
