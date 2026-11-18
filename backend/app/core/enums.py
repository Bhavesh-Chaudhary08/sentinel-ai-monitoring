"""Shared enums.

Member *names* are kept identical to their values on purpose: SQLModel maps
(str, Enum) fields to native Postgres ENUM columns, and SQLAlchemy persists
the member name while Pydantic serializes the value — identical names remove
any ambiguity about what ends up in the database.
"""

from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    employee = "employee"


class AiTool(str, Enum):
    chatgpt = "chatgpt"
    gemini = "gemini"
    claude = "claude"
    copilot = "copilot"
    other = "other"


class RiskCategory(str, Enum):
    none = "none"
    pii = "pii"
    source_code = "source_code"
    financial = "financial"
    confidential = "confidential"
    credentials = "credentials"
    other = "other"


class PolicyAction(str, Enum):
    log_only = "log_only"
    warn = "warn"
    block = "block"


class ClassificationStatus(str, Enum):
    pending = "pending"
    complete = "complete"
    failed = "failed"
    skipped = "skipped"  # navigation/visit events carry no prompt to classify


class ShadowRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


class TimeSegmentKind(str, Enum):
    """What a browser-time segment attributes its seconds to.

    tab:  the browser window was focused on this domain/path.
    away: the browser was unfocused (another app / locked) OR the machine was
          idle — active/idle seconds inside the segment say which.
    """

    tab = "tab"
    away = "away"
