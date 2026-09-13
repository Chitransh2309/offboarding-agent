"""integration_connections.settings — generic per-connection config,
starting with Notion's reports parent page id

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("integration_connections", sa.Column("settings", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("integration_connections", "settings")
