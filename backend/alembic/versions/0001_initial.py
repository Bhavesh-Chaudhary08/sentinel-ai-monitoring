"""Initial schema: user, policy_rule, captured_interaction, classification_finding.

Notes:
- Enum columns use native Postgres ENUM types, matching how SQLModel maps
  (str, Enum) fields (SQLModel >= 0.0.9). Type names are derived from the enum
  class name by SQLAlchemy on both sides, so model and migration agree.
- Column-level index=True / unique=True mirror the SQLModel Field flags, so
  index naming (ix_<table>_<column>) matches what the ORM expects.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.enums import (
    AiTool,
    ClassificationStatus,
    PolicyAction,
    RiskCategory,
    ShadowRisk,
    UserRole,
)

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, index=True, unique=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("role", sa.Enum(UserRole, native_enum=True), nullable=False, index=True),
        sa.Column("department", sa.String(length=120), nullable=True, index=True),
        sa.Column("job_title", sa.String(length=120), nullable=True),
        sa.Column("device_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("extension_version", sa.String(length=32), nullable=True),
        sa.Column("is_enrolled", sa.Boolean(), nullable=False),
        sa.Column("consent_accepted", sa.Boolean(), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=True),
        sa.Column("consent_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_role_active", "user", ["role", "is_active"])

    op.create_table(
        "policy_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, index=True, unique=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, index=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("category", sa.Enum(RiskCategory, native_enum=True), nullable=True, index=True),
        sa.Column("ai_tool", sa.Enum(AiTool, native_enum=True), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("role_scope", sa.Enum(UserRole, native_enum=True), nullable=True, index=True),
        sa.Column("department_scope", sa.String(length=120), nullable=True),
        sa.Column("action", sa.Enum(PolicyAction, native_enum=True), nullable=False, index=True),
        sa.Column("warn_message", sa.String(length=500), nullable=True),
        sa.Column("block_message", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_rule_active_priority", "policy_rule", ["is_active", "priority"]
    )

    op.create_table(
        "captured_interaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("client_event_id", sa.String(length=64), nullable=False),
        sa.Column("ai_tool", sa.Enum(AiTool, native_enum=True), nullable=False, index=True),
        sa.Column("domain", sa.String(length=255), nullable=False, index=True),
        sa.Column("page_path", sa.String(length=512), nullable=True),
        sa.Column("is_known_platform", sa.Boolean(), nullable=False, index=True),
        sa.Column("is_first_seen", sa.Boolean(), nullable=False),
        sa.Column("shadow_risk", sa.Enum(ShadowRisk, native_enum=True), nullable=True),
        sa.Column("prompt_text", sa.String(), nullable=True),
        sa.Column("response_text", sa.String(), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True, index=True),
        sa.Column("redacted_preview", sa.String(length=1000), nullable=True),
        sa.Column(
            "classification_status",
            sa.Enum(ClassificationStatus, native_enum=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "risk_category", sa.Enum(RiskCategory, native_enum=True), nullable=False, index=True
        ),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("classifier_version", sa.String(length=64), nullable=True),
        sa.Column("is_flagged", sa.Boolean(), nullable=False, index=True),
        sa.Column("policy_rule_id", sa.Uuid(), nullable=True),
        sa.Column("applied_action", sa.Enum(PolicyAction, native_enum=True), nullable=True),
        sa.Column("was_blocked", sa.Boolean(), nullable=False),
        sa.Column("content_stored", sa.Boolean(), nullable=False),
        sa.Column("purge_after", sa.DateTime(), nullable=True, index=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["policy_rule_id"], ["policy_rule.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_event_id", name="uq_interaction_user_event"),
    )
    op.create_index(
        "ix_interaction_user_occurred", "captured_interaction", ["user_id", "occurred_at"]
    )
    op.create_index(
        "ix_interaction_category_occurred",
        "captured_interaction",
        ["risk_category", "occurred_at"],
    )
    op.create_index(
        "ix_interaction_domain_known", "captured_interaction", ["domain", "is_known_platform"]
    )

    op.create_table(
        "classification_finding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interaction_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("engine", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=True),
        sa.Column("end", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["interaction_id"], ["captured_interaction.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finding_interaction_score", "classification_finding", ["interaction_id", "score"]
    )


def downgrade() -> None:
    # Reverse order (FK dependencies).
    op.drop_table("classification_finding")
    op.drop_table("captured_interaction")
    op.drop_table("policy_rule")
    op.drop_table("user")

    # drop_table removes indexes/constraints but not Postgres enum types.
    for enum_cls in (
        AiTool,
        ClassificationStatus,
        PolicyAction,
        RiskCategory,
        ShadowRisk,
        UserRole,
    ):
        # IF EXISTS keeps this safe even if SQLAlchemy derived a different name.
        op.execute(f"DROP TYPE IF EXISTS {enum_cls.__name__.lower()}")
