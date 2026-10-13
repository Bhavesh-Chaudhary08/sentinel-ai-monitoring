"""Public metadata the extension bootstraps from (domain list, consent version)."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/ai-domains")
def ai_domains() -> dict:
    """Single source of truth for 'known AI platform'.

    The extension fetches this on install/startup and caches it with a baked-in
    fallback, so ops can extend coverage without shipping a new extension build.
    """
    return {
        "domains": settings.known_ai_domains,
        "consent_version": settings.consent_version,
        "presidio_enabled": settings.presidio_enabled,
        "semantic_enabled": settings.semantic_enabled,
    }
