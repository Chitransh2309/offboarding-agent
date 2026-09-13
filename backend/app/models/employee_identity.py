import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import SystemType


class EmployeeIdentity(Base, UUIDPKMixin):
    """Canonical employee -> per-system account, resolved once at sync time
    rather than re-derived by search on every offboarding run."""

    __tablename__ = "employee_identities"
    __table_args__ = (
        sa.UniqueConstraint("system", "external_id", name="uq_identity_system_external_id"),
        sa.UniqueConstraint("employee_id", "system", name="uq_identity_employee_system"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    system: Mapped[SystemType] = mapped_column(pg_enum(SystemType, "identity_system_type"), nullable=False)
    external_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    external_handle: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
