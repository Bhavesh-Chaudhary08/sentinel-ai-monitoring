"""Application settings via pydantic-settings.

Every value can be overridden by an environment variable of the same name,
which is how docker-compose passes configuration through.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- app ---
    project_name: str = "AI Usage Monitoring & DLP"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # --- infra ---
    database_url: str = "postgresql+psycopg2://aidlp:aidlp@localhost:5432/aidlp"
    redis_url: str = "redis://localhost:6379/0"

    # --- auth ---
    secret_key: str = "dev-only-insecure-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # --- consent / capture ---
    consent_version: str = "2026.01"
    max_prompt_chars: int = 8000
    max_response_chars: int = 8000
    redacted_preview_chars: int = 400
    # Process classification inside the request instead of the Celery worker
    # (used by the test-suite; keeps dev runs simple without Redis).
    classify_sync: bool = False
    # --- single-process (free-hosting) mode ---
    # When there is no Celery beat either (free PaaS tiers run ONE web
    # process), the retention/stale sweeps run in-process. Defaults to
    # CLASSIFY_SYNC when unset, so no-worker deployments get sweeps for free
    # while compose deployments (worker+beat present) keep them in beat.
    inline_scheduler: bool | None = None
    # Serve the built dashboard from this process (single origin) when this
    # points at a directory of static files — used by the PaaS image
    # (FRONTEND_DIR=/srv/frontend). Unset → API-only (compose uses nginx).
    frontend_dir: str | None = None

    # --- capture storage mode / retention ---
    # Prompts-only monitoring: AI response text is never stored. Responses are
    # still used client-side as the trigger that flushes the paired prompt.
    capture_responses: bool = False
    # "full":    every prompt is stored verbatim and classified risky/safe
    #            (demo/forensic mode — pair with a short retention_days_full).
    # "minimal": raw text is retained ONLY for flagged interactions; everything
    #            else is reduced to a sha256 hash + redacted preview at ingest.
    storage_mode: str = "full"
    store_raw_when_flagged: bool = True
    retention_days_default: int = 30
    retention_days_flagged: int = 180
    retention_days_full: int = 30

    # --- classification ---
    presidio_enabled: bool = True
    semantic_enabled: bool = True
    spacy_model: str = "en_core_web_sm"
    semantic_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Minimum similarity for a semantic/lexical category to count as a match.
    semantic_threshold: float = 0.45
    lexical_threshold: float = 0.30
    # Score at which an interaction becomes "flagged" (raw text retained).
    flag_threshold: float = 0.50

    # --- alerting ---
    # warn-action interactions only raise an alert above this confidence.
    alert_min_score: float = 0.75
    critical_score: float = 0.95

    # --- misc ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Known AI platforms (single source of truth — the extension fetches this
    # list from GET /api/v1/meta/ai-domains). Override with a JSON array.
    known_ai_domains: list[str] = [
        "chat.openai.com",
        "chatgpt.com",
        "openai.com",
        "gemini.google.com",
        "aistudio.google.com",
        "claude.ai",
        "anthropic.com",
        "copilot.microsoft.com",
        "github.com",
        "perplexity.ai",
        "poe.com",
        "character.ai",
        "you.com",
        "deepseek.com",
        "mistral.ai",
        "huggingface.co",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
