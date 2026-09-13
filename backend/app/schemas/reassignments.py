from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ActionStatus, SuggestedBy, VerifyStatus


class ReassignmentActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_item_id: UUID
    suggested_owner_id: UUID | None
    suggested_by: SuggestedBy
    justification: str | None = None
    confirmed_owner_id: UUID | None
    reassign_status: ActionStatus
    verify_status: VerifyStatus
    error_message: str | None


class ConfirmReassignmentRequest(BaseModel):
    confirmed_owner_id: UUID
