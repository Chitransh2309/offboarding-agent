import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin


class LLMInvocation(Base, UUIDPKMixin):
    """One row per call through llm_client.invoke(), logged from inside
    invoke() itself so every caller is covered automatically — narration,
    disambiguation, reassignment justification, skill tagging — without
    each call site remembering to log. Best-effort only: a logging failure
    must never take down the LLM call it's trying to record."""

    __tablename__ = "llm_invocations"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    system_prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    response: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
