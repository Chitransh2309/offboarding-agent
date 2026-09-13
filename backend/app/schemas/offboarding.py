from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ActionStatus, EnvironmentType, RunStatus, VerifyStatus


class StartRunRequest(BaseModel):
    employee_id: UUID
    environment: EnvironmentType


class RevocationActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    access_grant_id: UUID
    revoke_status: ActionStatus
    verify_status: VerifyStatus
    error_message: str | None


class OffboardingRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    environment: EnvironmentType
    status: RunStatus
    initiated_at: datetime
    completed_at: datetime | None


class OffboardingRunDetailOut(OffboardingRunOut):
    revocation_actions: list[RevocationActionOut]
    narrative: str | None = None
    notion_report_url: str | None = None
