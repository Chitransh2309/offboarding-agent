from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import EmployeeStatus, GrantStatus, SystemType, WorkItemStatus


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    company_email: str
    department: str | None
    manager_id: UUID | None
    status: EmployeeStatus


class AccessGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    system: SystemType
    grant_type: str
    external_id: str
    resource_name: str | None
    role: str | None
    status: GrantStatus
    last_synced_at: datetime | None


class WorkItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    system: SystemType
    item_type: str
    title: str | None
    url: str | None
    status: WorkItemStatus
    skill_tags: list[str] | None


class EmployeeDetailOut(EmployeeOut):
    access_grants: list[AccessGrantOut]
    work_items: list[WorkItemOut]


class SystemResyncResult(BaseModel):
    system: SystemType
    discovered: int
    linked: int
    skipped: int


class ResyncResultOut(BaseModel):
    results: list[SystemResyncResult]
