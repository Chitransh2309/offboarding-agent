import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import ActionStatus, VerifyStatus


class RevocationAction(Base, UUIDPKMixin):
    """One row per atomic revoke_and_verify call. revoke_status and
    verify_status are separate columns so a revoke that "succeeded" but
    failed verification stays visible, never collapsed into one flag."""

    __tablename__ = "revocation_actions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"), nullable=False
    )
    access_grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("access_grants.id"), nullable=False
    )
    revoke_status: Mapped[ActionStatus] = mapped_column(
        pg_enum(ActionStatus, "revoke_action_status"), nullable=False, default=ActionStatus.PENDING
    )
    revoke_attempted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    verify_status: Mapped[VerifyStatus] = mapped_column(
        pg_enum(VerifyStatus, "revoke_verify_status"), nullable=False, default=VerifyStatus.PENDING
    )
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
