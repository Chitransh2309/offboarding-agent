import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import ActionStatus, SuggestedBy, VerifyStatus


class ReassignmentAction(Base, UUIDPKMixin):
    """One row per atomic reassign_and_verify call. suggested_owner_id is
    the LLM's proposal; confirmed_owner_id stays null until a human
    approves it, and only a confirmed row is eligible to execute."""

    __tablename__ = "reassignment_actions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"), nullable=False
    )
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("work_items.id"), nullable=False
    )
    suggested_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True
    )
    suggested_by: Mapped[SuggestedBy] = mapped_column(
        pg_enum(SuggestedBy, "suggested_by_type"), nullable=False, default=SuggestedBy.LLM
    )
    justification: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    confirmed_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True
    )
    reassign_status: Mapped[ActionStatus] = mapped_column(
        pg_enum(ActionStatus, "reassign_action_status"), nullable=False, default=ActionStatus.PENDING
    )
    reassign_attempted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    verify_status: Mapped[VerifyStatus] = mapped_column(
        pg_enum(VerifyStatus, "reassign_verify_status"), nullable=False, default=VerifyStatus.PENDING
    )
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
