"""GitHub App JWT + installation token minting. A GitHub App is installed
at the org level (not tied to any one admin's personal OAuth token), so the
integration survives even if the connecting admin later leaves — see
Implementation_Plan.pdf's per-platform connection table.

NOTE: installation tokens expire after ~1 hour. This module mints one at
connect time for storage; a production deployment should re-mint on use
(or on a schedule) rather than relying on the one stored at connect time
still being valid days later. Flagging this rather than silently storing
a token that will go stale."""

from __future__ import annotations

import time

import httpx
from jose import jwt as jose_jwt

from app.config import get_settings


def _app_jwt() -> str:
    settings = get_settings()
    if not settings.github_app_id or not settings.github_app_private_key:
        raise RuntimeError("GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY not configured")

    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": settings.github_app_id}
    return jose_jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")


def _app_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_app_jwt()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def mint_installation_token(installation_id: str) -> str:
    settings = get_settings()
    resp = httpx.post(
        f"{settings.github_api_base_url}/app/installations/{installation_id}/access_tokens",
        headers=_app_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def get_installation(installation_id: str) -> dict:
    """Confirms an installation_id is real and currently active for OUR
    app, rather than trusting it at face value from a callback redirect.
    GitHub's own docs warn the installation_id in a setup-URL redirect can
    be spoofed by hitting the callback directly with a fabricated value —
    this call fails (404/410) for anything that isn't a genuine, currently
    active installation of this app."""
    settings = get_settings()
    resp = httpx.get(
        f"{settings.github_api_base_url}/app/installations/{installation_id}",
        headers=_app_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def update_webhook_config(url: str, secret: str | None) -> dict:
    """PATCH /app/hook/config — the one webhook URL/secret shared across
    every installation of this app. Requires the app JWT specifically;
    installation tokens and user tokens are rejected for this endpoint."""
    settings = get_settings()
    body: dict = {"url": url, "content_type": "json"}
    if secret:
        body["secret"] = secret
    resp = httpx.patch(
        f"{settings.github_api_base_url}/app/hook/config",
        headers=_app_headers(),
        json=body,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()
