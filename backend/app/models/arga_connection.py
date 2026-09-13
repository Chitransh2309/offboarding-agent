import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import ConnectionStatus


class ArgaConnection(Base, UUIDPKMixin):
    """The org's own Arga Labs account, used to provision sandbox twins on
    their plan/quota — never ours. One per organization."""

    __tablename__ = "arga_connections"
    __table_args__ = (sa.UniqueConstraint("organization_id", name="uq_arga_connections_org"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    encrypted_api_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    connected_by: Mapped[str] = mapped_column(sa.Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    status: Mapped[ConnectionStatus] = mapped_column(
        pg_enum(ConnectionStatus, "arga_connection_status"),
        nullable=False,
        default=ConnectionStatus.ACTIVE,
    )
