from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ConnectionStatus, EnvironmentType, SystemType


class IntegrationConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    system: SystemType
    environment: EnvironmentType
    status: ConnectionStatus
    connected_at: datetime


class ConnectAuthorizeUrlOut(BaseModel):
    authorize_url: str


class ArgaConnectRequest(BaseModel):
    api_key: str


class SandboxProvisionRequest(BaseModel):
    ttl_minutes: int = 120
    scenario_prompt: str | None = None


class NotionReportSettingsRequest(BaseModel):
    reports_parent_page_id: str


class NotionPageOut(BaseModel):
    id: str
    title: str
