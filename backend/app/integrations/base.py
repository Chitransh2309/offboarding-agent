from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import get_settings
from app.models.enums import SystemType

if TYPE_CHECKING:
    from app.models import AccessGrant, IntegrationConnection, WorkItem


@dataclass(frozen=True)
class AccessGrantData:
    """What list_access() returns for one grant found on the remote system —
    not yet an AccessGrant row, sync_service reconciles this against the DB."""

    grant_type: str
    external_id: str
    resource_name: str | None
    role: str | None


@dataclass(frozen=True)
class MemberData:
    """One person found in the connected workspace/org — used to discover
    employees, not just enrich ones already in the DB. email may be None
    where the provider's API doesn't expose it (e.g. Slack without the
    users:read.email scope, or GitHub org members generally)."""

    external_id: str
    external_handle: str | None
    email: str | None


@dataclass(frozen=True)
class WorkItemData:
    item_type: str
    external_id: str
    title: str | None
    url: str | None
    status: str


@dataclass(frozen=True)
class ActionResult:
    success: bool
    raw_response: dict | None = None
    error_message: str | None = None


class IntegrationClient(ABC):
    """Common interface every system's client implements. base_url is
    whatever integration_connections row supplied it — a real provider API
    for environment=production, an Arga twin's base URL for environment=
    sandbox. Callers (execution_service, sync_service) never branch on
    environment; only this construction point does."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    @abstractmethod
    def list_members(self) -> list[MemberData]: ...

    @abstractmethod
    def list_access(self, employee_external_id: str, employee_external_handle: str | None) -> list[AccessGrantData]: ...

    @abstractmethod
    def list_work_items(self, employee_external_id: str, employee_external_handle: str | None) -> list[WorkItemData]: ...

    @abstractmethod
    def revoke(self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None) -> ActionResult: ...

    @abstractmethod
    def verify_revoked(self, grant: "AccessGrant", employee_external_id: str, employee_external_handle: str | None) -> bool: ...

    @abstractmethod
    def reassign(self, work_item: "WorkItem", new_owner_external_id: str) -> ActionResult: ...

    @abstractmethod
    def verify_reassigned(self, work_item: "WorkItem", new_owner_external_id: str) -> bool: ...


def _resolve_token(connection: "IntegrationConnection") -> str:
    """GitHub App installation tokens expire after ~1 hour — trusting the
    one stored at connect time silently 401s every call once it's stale
    (this is exactly what happened on the first real offboarding run).
    For GitHub in production, mint a fresh token on every use instead;
    every other case still uses the stored, encrypted token, since Slack/
    Notion/Linear OAuth tokens and twin credentials don't expire the same
    way."""
    from app.models.enums import EnvironmentType, SystemType as _SystemType
    from app.security import decrypt_token

    if connection.system == _SystemType.GITHUB and connection.environment == EnvironmentType.PRODUCTION:
        from app.integrations.github_app_auth import mint_installation_token

        if not connection.external_ref:
            raise ValueError("GitHub connection is missing its installation_id (external_ref)")
        return mint_installation_token(connection.external_ref)

    return decrypt_token(connection.encrypted_token)


def get_client(connection: "IntegrationConnection", token: str | None = None) -> IntegrationClient:
    """Builds the right client for a connection row. Sandbox connections
    carry their twin base URL in external_ref; production connections use
    the fixed real-provider base URL from settings. Token resolution is
    handled internally now (see _resolve_token) — pass an explicit token
    only to override that, which normal callers should never need to do."""
    from app.models.enums import EnvironmentType

    settings = get_settings()

    if connection.environment == EnvironmentType.SANDBOX:
        if not connection.external_ref:
            raise ValueError("sandbox connection is missing its twin base URL (external_ref)")
        base_url = connection.external_ref
    else:
        base_url = {
            SystemType.GITHUB: settings.github_api_base_url,
            SystemType.SLACK: settings.slack_api_base_url,
            SystemType.NOTION: settings.notion_api_base_url,
            SystemType.LINEAR: settings.linear_api_base_url,
        }[connection.system]

    from app.integrations.github_client import GitHubClient
    from app.integrations.linear_client import LinearClient
    from app.integrations.notion_client import NotionClient
    from app.integrations.slack_client import SlackClient

    client_cls = {
        SystemType.GITHUB: GitHubClient,
        SystemType.SLACK: SlackClient,
        SystemType.NOTION: NotionClient,
        SystemType.LINEAR: LinearClient,
    }[connection.system]

    resolved_token = token if token is not None else _resolve_token(connection)
    return client_cls(base_url=base_url, token=resolved_token)
