import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import SystemType, WorkItemStatus


class WorkItem(Base, UUIDPKMixin):
    """Memory layer for tasks, same sync pattern as access_grants.
    skill_tags/skill_tagged_at are filled by the daily skill_tagging_service
    and feed the reassignment suggester's skill-overlap matching."""

    __tablename__ = "work_items"
    __table_args__ = (
        sa.UniqueConstraint("system", "external_id", name="uq_work_item_system_external_id"),
        sa.Index("ix_work_items_employee_status", "employee_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    system: Mapped[SystemType] = mapped_column(pg_enum(SystemType, "work_item_system_type"), nullable=False)
    item_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    external_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[WorkItemStatus] = mapped_column(
        pg_enum(WorkItemStatus, "work_item_status"), nullable=False, default=WorkItemStatus.OPEN
    )
    skill_tags: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    skill_tagged_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
