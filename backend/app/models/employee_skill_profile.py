import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin


class EmployeeSkillProfile(Base, UUIDPKMixin):
    """Memory-layer aggregate over work_items.skill_tags, refreshed by the
    daily skill_tagging_service. Lets reassignment suggestion do an instant
    lookup instead of scanning years of work_items at request time."""

    __tablename__ = "employee_skill_profile"
    __table_args__ = (sa.UniqueConstraint("employee_id", "skill_tag", name="uq_skill_profile_employee_tag"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    skill_tag: Mapped[str] = mapped_column(sa.Text, nullable=False)
    task_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_active_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
