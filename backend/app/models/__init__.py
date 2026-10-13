"""SQLModel table definitions.

Importing every model here means `SQLModel.metadata` is fully populated with a
single `import app.models` (used by alembic/env.py and init_db).
"""

from app.models.alert import Alert
from app.models.audit import AuditLog
from app.models.interaction import CapturedInteraction, ClassificationFinding
from app.models.policy import PolicyRule
from app.models.user import User

__all__ = [
    "User",
    "CapturedInteraction",
    "ClassificationFinding",
    "PolicyRule",
    "Alert",
    "AuditLog",
]
