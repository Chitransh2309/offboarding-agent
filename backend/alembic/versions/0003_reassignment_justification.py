"""reassignment_actions.justification — explanatory text for the suggested
owner, shown in the confirm UI

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reassignment_actions", sa.Column("justification", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("reassignment_actions", "justification")
