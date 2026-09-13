"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "arga_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("encrypted_api_key", sa.Text, nullable=False),
        sa.Column("connected_by", sa.Text, nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "expired", "invalid", name="arga_connection_status"),
            nullable=False,
            server_default="active",
        ),
        sa.UniqueConstraint("organization_id", name="uq_arga_connections_org"),
    )

    op.create_table(
        "integration_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("system", sa.Enum("github", "slack", "notion", "linear", name="system_type"), nullable=False),
        sa.Column(
            "environment", sa.Enum("sandbox", "production", name="environment_type"), nullable=False
        ),
        sa.Column("encrypted_token", sa.Text, nullable=False),
        sa.Column("external_ref", sa.Text, nullable=True),
        sa.Column("scopes_granted", ARRAY(sa.Text), nullable=True),
        sa.Column("connected_by", sa.Text, nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "expired", "invalid", name="integration_connection_status"),
            nullable=False,
            server_default="active",
        ),
        sa.UniqueConstraint(
            "organization_id", "system", "environment", name="uq_integration_connection_org_system_env"
        ),
    )

    op.create_table(
        "employees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("company_email", sa.Text, nullable=False),
        sa.Column("department", sa.Text, nullable=True),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "departing", "offboarded", name="employee_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "company_email", name="uq_employee_org_email"),
    )

    op.create_table(
        "employee_identities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "system", sa.Enum("github", "slack", "notion", "linear", name="identity_system_type"), nullable=False
        ),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("external_handle", sa.Text, nullable=True),
        sa.UniqueConstraint("system", "external_id", name="uq_identity_system_external_id"),
        sa.UniqueConstraint("employee_id", "system", name="uq_identity_employee_system"),
    )

    op.create_table(
        "access_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "system",
            sa.Enum("github", "slack", "notion", "linear", name="access_grant_system_type"),
            nullable=False,
        ),
        sa.Column("grant_type", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("resource_name", sa.Text, nullable=True),
        sa.Column("role", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "revoke_failed", name="grant_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "employee_id", "system", "grant_type", "external_id", name="uq_access_grant_identity"
        ),
    )
    op.create_index("ix_access_grants_employee_status", "access_grants", ["employee_id", "status"])

    op.create_table(
        "work_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "system", sa.Enum("github", "slack", "notion", "linear", name="work_item_system_type"), nullable=False
        ),
        sa.Column("item_type", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "blocked", "closed", name="work_item_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("skill_tags", ARRAY(sa.Text), nullable=True),
        sa.Column("skill_tagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("system", "external_id", name="uq_work_item_system_external_id"),
    )
    op.create_index("ix_work_items_employee_status", "work_items", ["employee_id", "status"])

    op.create_table(
        "employee_skill_profile",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("skill_tag", sa.Text, nullable=False),
        sa.Column("task_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("employee_id", "skill_tag", name="uq_skill_profile_employee_tag"),
    )

    op.create_table(
        "offboarding_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("initiated_by", sa.Text, nullable=False),
        sa.Column(
            "environment", sa.Enum("sandbox", "production", name="run_environment_type"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("in_progress", "completed", "completed_with_errors", "failed", name="run_status"),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("initiated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "revocation_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", UUID(as_uuid=True), sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("access_grant_id", UUID(as_uuid=True), sa.ForeignKey("access_grants.id"), nullable=False),
        sa.Column(
            "revoke_status",
            sa.Enum("pending", "success", "failed", name="revoke_action_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("revoke_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verify_status",
            sa.Enum("pending", "verified", "still_present", "error", name="revoke_verify_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("raw_response", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "reassignment_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", UUID(as_uuid=True), sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("work_item_id", UUID(as_uuid=True), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("suggested_owner_id", UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column(
            "suggested_by",
            sa.Enum("llm", "human", name="suggested_by_type"),
            nullable=False,
            server_default="llm",
        ),
        sa.Column("confirmed_owner_id", UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column(
            "reassign_status",
            sa.Enum("pending", "success", "failed", name="reassign_action_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reassign_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verify_status",
            sa.Enum("pending", "verified", "still_present", "error", name="reassign_verify_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("reassignment_actions")
    op.drop_table("revocation_actions")
    op.drop_table("offboarding_runs")
    op.drop_table("employee_skill_profile")
    op.drop_table("work_items")
    op.drop_table("access_grants")
    op.drop_table("employee_identities")
    op.drop_table("employees")
    op.drop_table("integration_connections")
    op.drop_table("arga_connections")
    op.drop_table("organizations")

    sa.Enum(name="reassign_verify_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reassign_action_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="suggested_by_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="revoke_verify_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="revoke_action_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="run_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="run_environment_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="work_item_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="work_item_system_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="grant_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="access_grant_system_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="identity_system_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="employee_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="integration_connection_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="environment_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="system_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="arga_connection_status").drop(op.get_bind(), checkfirst=True)
