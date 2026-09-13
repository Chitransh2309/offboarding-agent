"""reassignment_actions.raw_response — the raw API response from a reassign
call, same pattern as revocation_actions.raw_response. llm_invocations —
audit trail of every LLM call (purpose, prompts, response), logged from
inside llm_client.invoke() itself.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reassignment_actions", sa.Column("raw_response", JSONB, nullable=True))

    op.create_table(
        "llm_invocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("user_prompt", sa.Text, nullable=False),
        sa.Column("response", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_llm_invocations_organization_id", "llm_invocations", ["organization_id"])
    op.create_index("ix_llm_invocations_run_id", "llm_invocations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_invocations_run_id", table_name="llm_invocations")
    op.drop_index("ix_llm_invocations_organization_id", table_name="llm_invocations")
    op.drop_table("llm_invocations")
    op.drop_column("reassignment_actions", "raw_response")
