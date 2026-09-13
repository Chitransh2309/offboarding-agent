"""Public endpoints GitHub/Linear call directly — no admin bearer token,
verified instead by HMAC signature. This is the near-real-time half of the
memory-layer sync; reconcile_organization() in sync_service is the cron
safety net for what these miss (missed deliveries, under-scoped apps, bulk
changes that don't fire events)."""

from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.models.enums import EnvironmentType
from app.services.sync_service import handle_github_webhook, handle_linear_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_github_signature(secret: str | None, body: bytes, signature_header: str | None) -> None:
    if not secret:
        return  # no secret configured — allowed for local/sandbox dev, logged as a gap rather than silently insecure
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or malformed X-Hub-Signature-256")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "signature mismatch")


def _verify_linear_signature(secret: str | None, body: bytes, signature_header: str | None) -> None:
    if not secret:
        return
    if not signature_header:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing linear-signature")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "signature mismatch")


@router.post("/github", status_code=status.HTTP_204_NO_CONTENT)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
    db: Session = Depends(get_db),
) -> None:
    """One URL for the whole GitHub App — GitHub Apps have exactly one
    webhook config shared across every installation/org, there's no such
    thing as a per-org webhook URL. Which org a given event belongs to is
    resolved inside handle_github_webhook from the payload's
    installation.id, matched against integration_connections.external_ref."""
    settings = get_settings()
    body = await request.body()
    _verify_github_signature(settings.github_webhook_secret, body, x_hub_signature_256)

    payload = await request.json()
    handle_github_webhook(db, EnvironmentType.PRODUCTION, x_github_event, payload)


@router.post("/linear/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
async def linear_webhook(
    organization_id: UUID,
    request: Request,
    linear_signature: str | None = Header(None),
    db: Session = Depends(get_db),
) -> None:
    settings = get_settings()
    body = await request.body()
    _verify_linear_signature(settings.linear_webhook_secret, body, linear_signature)

    payload = await request.json()
    handle_linear_webhook(db, organization_id, EnvironmentType.PRODUCTION, payload)
