import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import GrantStatus, SystemType


class AccessGrant(Base, UUIDPKMixin):
    """Memory layer for access. Kept warm by webhook/cron sync; treated as a
    cache, not ground truth, at the moment a revoke actually runs — see
    execution_service's live targeted re-check."""

    __tablename__ = "access_grants"
    __table_args__ = (
        sa.UniqueConstraint(
            "employee_id", "system", "grant_type", "external_id", name="uq_access_grant_identity"
        ),
        sa.Index("ix_access_grants_employee_status", "employee_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    system: Mapped[SystemType] = mapped_column(pg_enum(SystemType, "access_grant_system_type"), nullable=False)
    grant_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    external_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    resource_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    role: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[GrantStatus] = mapped_column(
        pg_enum(GrantStatus, "grant_status"), nullable=False, default=GrantStatus.ACTIVE
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
