import hashlib
import hmac
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentAdmin, get_current_admin, get_db
from app.config import get_settings
from app.integrations.arga_provisioning import ArgaProvisioningError, provision_sandbox_for_organization
from app.integrations.demo_scenario import OFFBOARDING_DEMO_SCENARIO_PROMPT
from app.integrations.base import get_client
from app.integrations.github_app_auth import get_installation, mint_installation_token
from app.integrations.notion_client import NotionClient
from app.models import ArgaConnection, IntegrationConnection
from app.models.enums import ConnectionStatus, EnvironmentType, SystemType
from app.schemas.integrations import (
    ArgaConnectRequest,
    ConnectAuthorizeUrlOut,
    IntegrationConnectionOut,
    NotionPageOut,
    NotionReportSettingsRequest,
    SandboxProvisionRequest,
)
from app.services.reporting_service import REPORTS_PARENT_PAGE_KEY
from app.security import decrypt_token, encrypt_token
from app.services.sync_service import discover_and_sync_connection

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationConnectionOut])
def list_connections(
    db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> list[IntegrationConnection]:
    return (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.organization_id == admin.organization_id)
        .all()
    )


@router.get("/notion/shared-pages", response_model=list[NotionPageOut])
def list_notion_shared_pages(
    db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> list[dict]:
    """Every page currently shared with the Notion integration, so an
    admin can pick one from a list instead of pasting a raw page id —
    there's no way to discover pages that haven't been explicitly shared
    with the integration at all, so an empty list here means exactly that."""
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.organization_id == admin.organization_id,
            IntegrationConnection.system == SystemType.NOTION,
            IntegrationConnection.environment == EnvironmentType.PRODUCTION,
        )
        .first()
    )
    if connection is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "connect Notion first")

    client = get_client(connection)
    assert isinstance(client, NotionClient)
    return client.list_accessible_pages()


@router.patch("/notion/report-settings", status_code=status.HTTP_204_NO_CONTENT)
def set_notion_report_settings(
    body: NotionReportSettingsRequest,
    db: Session = Depends(get_db),
    admin: CurrentAdmin = Depends(get_current_admin),
) -> None:
    """The parent page id offboarding audit reports get written under.
    Reports are opt-in — nothing gets written to Notion until this is set."""
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.organization_id == admin.organization_id,
            IntegrationConnection.system == SystemType.NOTION,
            IntegrationConnection.environment == EnvironmentType.PRODUCTION,
        )
        .first()
    )
    if connection is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "connect Notion before configuring report settings")

    connection.settings = {**(connection.settings or {}), REPORTS_PARENT_PAGE_KEY: body.reports_parent_page_id}
    db.commit()


# --- Production OAuth: connect ---------------------------------------------


def _redirect_uri(system: SystemType) -> str:
    settings = get_settings()
    return f"{settings.app_base_url}/integrations/{system.value}/callback"


def _state(admin: CurrentAdmin) -> str:
    # State encodes org_id:admin_id so the public callback (no auth header
    # available on a browser redirect) knows who to attribute the
    # connection to — HMAC-signed so it can't be forged into connecting a
    # victim's OAuth grant to an attacker-controlled organization_id.
    settings = get_settings()
    payload = f"{admin.organization_id}:{admin.admin_id}"
    signature = hmac.new(settings.jwt_secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


@router.get("/{system}/authorize-url", response_model=ConnectAuthorizeUrlOut)
def get_authorize_url(
    system: SystemType, admin: CurrentAdmin = Depends(get_current_admin)
) -> ConnectAuthorizeUrlOut:
    settings = get_settings()
    state = _state(admin)
    redirect_uri = _redirect_uri(system)

    if system == SystemType.GITHUB:
        if not settings.github_app_slug:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "GITHUB_APP_SLUG not configured")
        url = f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}"
    elif system == SystemType.SLACK:
        params = {
            "client_id": settings.slack_client_id,
            # admin.users:read deliberately omitted — it's Enterprise Grid-only
            # and Slack's app manifest rejects it for a normal workspace app.
            # Full account deactivation stays unavailable outside Enterprise
            # Grid; channel-membership revoke (which these scopes do cover)
            # is the primary path. See slack_client.py's docstring.
            # channels:join lets the bot join public channels itself before
            # kicking someone — conversations.kick requires the bot to
            # already be a member, which is why revoke was failing with
            # not_in_channel on every real channel before this was added.
            "scope": "channels:read,channels:manage,channels:join,users:read,users:read.email",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        url = f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"
    elif system == SystemType.NOTION:
        params = {
            "client_id": settings.notion_client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        url = f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}"
    else:  # LINEAR
        params = {
            "client_id": settings.linear_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            # admin is required for userSuspend (the real revoke mutation
            # for workspace membership) — without it Linear returns a
            # FORBIDDEN "Access denied" GraphQL error on every revoke,
            # discovered from a real failed offboarding run. Granting this
            # scope still isn't enough on its own: the Linear account doing
            # the OAuth connect must itself be a workspace admin, or Linear
            # denies it the same way regardless of requested scope.
            "scope": "read,write,admin",
            # actor=app cannot hold admin rights at all — Linear rejects
            # the admin scope outright for app-attributed actions ("app
            # users cannot request admin scopes"), found when reconnecting
            # after adding the scope above. actor=user attributes every
            # action to the connecting account instead, so admin is only
            # as valid as that account's own real Linear permissions.
            "actor": "user",
            "state": state,
        }
        url = f"https://linear.app/oauth/authorize?{urlencode(params)}"

    return ConnectAuthorizeUrlOut(authorize_url=url)


class InvalidStateError(ValueError):
    pass


def _parse_state(state: str) -> tuple[UUID, UUID]:
    settings = get_settings()
    try:
        org_id_str, admin_id_str, signature = state.rsplit(":", 2)
    except ValueError as exc:
        raise InvalidStateError("malformed state") from exc

    payload = f"{org_id_str}:{admin_id_str}"
    expected = hmac.new(settings.jwt_secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise InvalidStateError("state signature mismatch — possible tampering")

    return UUID(org_id_str), UUID(admin_id_str)


def _integrations_page_redirect(**params: str) -> RedirectResponse:
    settings = get_settings()
    url = f"{settings.frontend_base_url}/integrations?{urlencode(params)}"
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _finish_connect(
    db: Session,
    organization_id: UUID,
    system: SystemType,
    token: str,
    external_ref: str | None,
    scopes: list[str] | None,
    connected_by: str,
) -> RedirectResponse:
    """Upserts the connection, then immediately discovers/syncs employees
    from it — this is the 'connect an app, get your employees' behavior:
    a real OAuth connection is not considered done until the roster has
    been pulled in, not just the token stored."""
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.system == system,
            IntegrationConnection.environment == EnvironmentType.PRODUCTION,
        )
        .first()
    )
    if connection is None:
        connection = IntegrationConnection(
            organization_id=organization_id,
            system=system,
            environment=EnvironmentType.PRODUCTION,
            connected_by=connected_by,
        )
        db.add(connection)

    connection.encrypted_token = encrypt_token(token)
    connection.external_ref = external_ref
    connection.scopes_granted = scopes
    connection.status = ConnectionStatus.ACTIVE
    db.commit()
    db.refresh(connection)

    try:
        sync_summary = discover_and_sync_connection(db, connection)
    except Exception as exc:
        # The connection itself succeeded and is saved — sync failing
        # (rate limit, transient error) shouldn't undo that. Surface it to
        # the frontend distinctly from an OAuth failure.
        return _integrations_page_redirect(
            connected=system.value, sync_error=str(exc)[:200]
        )

    return _integrations_page_redirect(
        connected=system.value,
        discovered=str(sync_summary["discovered"]),
        linked=str(sync_summary["linked"]),
        skipped=str(sync_summary["skipped"]),
    )


@router.get("/github/callback")
def github_callback(
    installation_id: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    try:
        org_id, admin_id = _parse_state(state)
    except InvalidStateError as exc:
        return _integrations_page_redirect(error="github", detail=str(exc))

    try:
        # GitHub's own docs warn installation_id in a setup-URL redirect
        # can be spoofed by hitting this callback directly with a
        # fabricated value — confirm it's a real, currently active
        # installation of THIS app before minting a token for it.
        get_installation(installation_id)
    except Exception as exc:
        return _integrations_page_redirect(error="github", detail=f"could not verify installation: {exc}"[:200])

    try:
        token = mint_installation_token(installation_id)
    except Exception as exc:
        return _integrations_page_redirect(error="github", detail=str(exc)[:200])
    return _finish_connect(
        db, org_id, SystemType.GITHUB, token, external_ref=installation_id, scopes=None, connected_by=str(admin_id)
    )


@router.get("/slack/callback")
def slack_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    try:
        org_id, admin_id = _parse_state(state)
    except InvalidStateError as exc:
        return _integrations_page_redirect(error="slack", detail=str(exc))
    resp = httpx.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": settings.slack_client_id,
            "client_secret": settings.slack_client_secret,
            "code": code,
            "redirect_uri": _redirect_uri(SystemType.SLACK),
        },
        timeout=30.0,
    ).json()
    if not resp.get("ok"):
        return _integrations_page_redirect(error="slack", detail=str(resp.get("error"))[:200])

    return _finish_connect(
        db,
        org_id,
        SystemType.SLACK,
        token=resp["access_token"],
        external_ref=resp["team"]["id"],
        scopes=resp.get("scope", "").split(","),
        connected_by=str(admin_id),
    )


@router.get("/notion/callback")
def notion_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    try:
        org_id, admin_id = _parse_state(state)
    except InvalidStateError as exc:
        return _integrations_page_redirect(error="notion", detail=str(exc))
    resp = httpx.post(
        "https://api.notion.com/v1/oauth/token",
        json={"grant_type": "authorization_code", "code": code, "redirect_uri": _redirect_uri(SystemType.NOTION)},
        auth=(settings.notion_client_id, settings.notion_client_secret),
        timeout=30.0,
    ).json()
    if "access_token" not in resp:
        return _integrations_page_redirect(error="notion", detail=str(resp)[:200])

    return _finish_connect(
        db,
        org_id,
        SystemType.NOTION,
        token=resp["access_token"],
        external_ref=resp.get("workspace_id"),
        scopes=None,
        connected_by=str(admin_id),
    )


@router.get("/linear/callback")
def linear_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    try:
        org_id, admin_id = _parse_state(state)
    except InvalidStateError as exc:
        return _integrations_page_redirect(error="linear", detail=str(exc))
    resp = httpx.post(
        "https://api.linear.app/oauth/token",
        data={
            "client_id": settings.linear_client_id,
            "client_secret": settings.linear_client_secret,
            "code": code,
            "redirect_uri": _redirect_uri(SystemType.LINEAR),
            "grant_type": "authorization_code",
        },
        timeout=30.0,
    ).json()
    if "access_token" not in resp:
        return _integrations_page_redirect(error="linear", detail=str(resp)[:200])

    return _finish_connect(
        db,
        org_id,
        SystemType.LINEAR,
        token=resp["access_token"],
        external_ref=None,
        scopes=resp.get("scope", "").split(",") if resp.get("scope") else None,
        connected_by=str(admin_id),
    )


# --- Sandbox: bring-your-own Arga Labs account ------------------------------


@router.post("/arga/connect", status_code=status.HTTP_204_NO_CONTENT)
def connect_arga(
    body: ArgaConnectRequest, db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> None:
    """Stores the org's OWN Arga Labs API key — never a shared key of
    ours. See docs/Arga_Labs_Sandbox_Setup.pdf."""
    existing = db.query(ArgaConnection).filter(ArgaConnection.organization_id == admin.organization_id).first()
    if existing is None:
        existing = ArgaConnection(organization_id=admin.organization_id, connected_by=admin.email)
        db.add(existing)

    existing.encrypted_api_key = encrypt_token(body.api_key)
    existing.status = ConnectionStatus.ACTIVE
    db.commit()


@router.post("/sandbox/provision", response_model=list[IntegrationConnectionOut])
def provision_sandbox(
    body: SandboxProvisionRequest,
    db: Session = Depends(get_db),
    admin: CurrentAdmin = Depends(get_current_admin),
) -> list[IntegrationConnection]:
    arga_connection = (
        db.query(ArgaConnection).filter(ArgaConnection.organization_id == admin.organization_id).first()
    )
    if arga_connection is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "no Arga Labs account connected — call /integrations/arga/connect first"
        )

    api_key = decrypt_token(arga_connection.encrypted_api_key)
    try:
        return provision_sandbox_for_organization(
            db,
            organization_id=admin.organization_id,
            admin_email=admin.email,
            api_key=api_key,
            scenario_prompt=body.scenario_prompt or OFFBOARDING_DEMO_SCENARIO_PROMPT,
            ttl_minutes=body.ttl_minutes,
        )
    except ArgaProvisioningError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
