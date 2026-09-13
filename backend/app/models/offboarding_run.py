import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import EnvironmentType, RunStatus


class OffboardingRun(Base, UUIDPKMixin):
    """Top-level audit record per execution."""

    __tablename__ = "offboarding_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False
    )
    initiated_by: Mapped[str] = mapped_column(sa.Text, nullable=False)
    environment: Mapped[EnvironmentType] = mapped_column(pg_enum(EnvironmentType, "run_environment_type"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), nullable=False, default=RunStatus.IN_PROGRESS
    )
    initiated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
