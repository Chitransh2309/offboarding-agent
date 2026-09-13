import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import ConnectionStatus, EnvironmentType, SystemType


class IntegrationConnection(Base, UUIDPKMixin):
    """One row per org's connection to a system, sandbox or production.
    Sandbox rows are populated from Arga twin provisioning results;
    production rows from the real OAuth/App-install flow. Downstream code
    (integrations/*_client.py) reads this row and does not care which path
    created it."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "system", "environment", name="uq_integration_connection_org_system_env"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    system: Mapped[SystemType] = mapped_column(pg_enum(SystemType, "system_type"), nullable=False)
    environment: Mapped[EnvironmentType] = mapped_column(pg_enum(EnvironmentType, "environment_type"), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(sa.Text, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    scopes_granted: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    connected_by: Mapped[str] = mapped_column(sa.Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    status: Mapped[ConnectionStatus] = mapped_column(
        pg_enum(ConnectionStatus, "integration_connection_status"),
        nullable=False,
        default=ConnectionStatus.ACTIVE,
    )
    # Generic per-connection config, starting with Notion's reports parent
    # page id (integration_connections.settings["notion_reports_parent_page_id"]).
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
