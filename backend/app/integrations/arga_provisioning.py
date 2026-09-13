"""Arga Labs sandbox twin provisioning.

Each organization brings its OWN Arga Labs API key (stored encrypted in
arga_connections) — we never provision on a shared key on their behalf.
See docs/Arga_Labs_Sandbox_Setup.pdf for the full design.

NOTE: request/response field names here are reconstructed from Arga's
published docs and examples, not a live spec pull — verify against
docs.argalabs.com/api-reference before depending on this in production,
per the caveat already flagged in that doc.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import ConnectionStatus, EnvironmentType, SystemType
from app.security import encrypt_token

_PROVISION_PATH = "/validate/twins/provision"
_STATUS_PATH = "/validate/twins/provision/{run_id}"
_EXTEND_PATH = "/validate/twins/provision/{run_id}/extend"
_TEARDOWN_PATH = "/validate/twins/provision/{run_id}/teardown"

SANDBOX_TWINS = ["github", "slack", "notion", "linear"]


class ArgaProvisioningError(RuntimeError):
    pass


def _client(api_key: str) -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=settings.arga_api_base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )


def start_provisioning(
    api_key: str,
    twins: list[str] = SANDBOX_TWINS,
    scenario_prompt: str | None = None,
    scenario_id: str | None = None,
    scenario_generation_mode: str = "thorough",
    ttl_minutes: int = 120,
    public: bool = False,
) -> str:
    """Kicks off provisioning, returns a run_id to poll."""
    body: dict = {"twins": twins, "ttl_minutes": ttl_minutes, "public": public}
    if scenario_id:
        body["scenario_id"] = scenario_id
    elif scenario_prompt:
        body["scenario_prompt"] = scenario_prompt
        body["scenario_generation_mode"] = scenario_generation_mode

    with _client(api_key) as client:
        resp = client.post(_PROVISION_PATH, json=body)
        if resp.status_code >= 400:
            raise ArgaProvisioningError(f"provisioning request failed: {resp.status_code} {resp.text}")
        return resp.json()["run_id"]


def get_status(api_key: str, run_id: str) -> dict:
    """Returns the raw status payload: {"status": "...", "twins": [...], "expires_at": "..."}"""
    with _client(api_key) as client:
        resp = client.get(_STATUS_PATH.format(run_id=run_id))
        if resp.status_code >= 400:
            raise ArgaProvisioningError(f"status check failed: {resp.status_code} {resp.text}")
        return resp.json()


def wait_until_ready(api_key: str, run_id: str, timeout_seconds: int = 180, poll_interval_seconds: int = 3) -> dict:
    """Polls until status == ready or timeout. Arga docs note provisioning
    typically completes within a minute."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = get_status(api_key, run_id)
        if status.get("status") == "ready":
            return status
        if status.get("status") == "failed":
            raise ArgaProvisioningError(f"twin provisioning failed: {status}")
        time.sleep(poll_interval_seconds)
    raise ArgaProvisioningError(f"twin provisioning did not become ready within {timeout_seconds}s")


def extend_ttl(api_key: str, run_id: str, additional_minutes: int) -> dict:
    with _client(api_key) as client:
        resp = client.post(_EXTEND_PATH.format(run_id=run_id), json={"additional_minutes": additional_minutes})
        if resp.status_code >= 400:
            raise ArgaProvisioningError(f"extend TTL failed: {resp.status_code} {resp.text}")
        return resp.json()


def teardown(api_key: str, run_id: str) -> None:
    with _client(api_key) as client:
        resp = client.post(_TEARDOWN_PATH.format(run_id=run_id))
        if resp.status_code >= 400:
            raise ArgaProvisioningError(f"teardown failed: {resp.status_code} {resp.text}")


def parse_expires_at(status_payload: dict) -> datetime | None:
    raw = status_payload.get("expires_at")
    return datetime.fromisoformat(raw) if raw else None


def provision_sandbox_for_organization(
    db: Session,
    organization_id: uuid.UUID,
    admin_email: str,
    api_key: str,
    scenario_prompt: str,
    ttl_minutes: int = 120,
) -> list:
    """Provisions all four twins under the org's own Arga account and
    upserts one integration_connections row per twin with
    environment=sandbox. Returns the upserted IntegrationConnection rows."""
    from app.models import IntegrationConnection

    run_id = start_provisioning(
        api_key=api_key,
        twins=SANDBOX_TWINS,
        scenario_prompt=scenario_prompt,
        scenario_generation_mode="thorough",
        ttl_minutes=ttl_minutes,
        public=False,
    )
    ready = wait_until_ready(api_key, run_id)

    connections = []
    for twin in ready.get("twins", []):
        system = SystemType(twin["name"])
        existing = (
            db.query(IntegrationConnection)
            .filter(
                IntegrationConnection.organization_id == organization_id,
                IntegrationConnection.system == system,
                IntegrationConnection.environment == EnvironmentType.SANDBOX,
            )
            .first()
        )
        if existing is None:
            existing = IntegrationConnection(
                organization_id=organization_id,
                system=system,
                environment=EnvironmentType.SANDBOX,
                connected_by=admin_email,
            )
            db.add(existing)

        existing.encrypted_token = encrypt_token(twin["credential"])
        existing.external_ref = twin["base_url"]
        existing.status = ConnectionStatus.ACTIVE
        connections.append(existing)

    db.commit()
    for conn in connections:
        db.refresh(conn)
    return connections
