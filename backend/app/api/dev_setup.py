"""Local-dev bootstrap only — mounted in main.py only when
ENVIRONMENT=development. Drives GitHub's App Manifest flow so registering
the GitHub App is "click one button" instead of manually filling ~10
fields across the GitHub UI: /dev-setup/github/manifest renders an
auto-submitting form to github.com/settings/apps/new, GitHub creates the
app and redirects back to manifest-callback with a one-time code, which we
exchange for the app's real credentials and write straight into .env."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.config import get_settings

router = APIRouter(prefix="/dev-setup", tags=["dev-setup"])

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


@router.get("/github/manifest", response_class=HTMLResponse)
def github_manifest_form() -> str:
    settings = get_settings()
    manifest = {
        "name": f"Offboarding Agent Dev {settings.app_base_url.split('//')[-1].split('.')[0][:20]}",
        "url": settings.app_base_url,
        # One webhook URL for the whole app — GitHub Apps don't support a
        # per-org webhook, every installation's events land here and get
        # routed by installation.id inside handle_github_webhook.
        "hook_attributes": {"url": f"{settings.app_base_url}/webhooks/github"},
        "redirect_url": f"{settings.app_base_url}/dev-setup/github/manifest-callback",
        "setup_url": f"{settings.app_base_url}/integrations/github/callback",
        "public": False,
        "default_permissions": {
            "members": "write",
            "administration": "write",
            "pull_requests": "write",
            "issues": "write",
            "metadata": "read",
        },
        "default_events": ["member", "organization", "team", "issues", "pull_request"],
    }
    manifest_json = json.dumps(manifest).replace('"', "&quot;")
    return f"""
    <html><body onload="document.forms[0].submit()">
      <p>Redirecting to GitHub to create the app...</p>
      <form action="https://github.com/settings/apps/new" method="post">
        <input type="hidden" name="manifest" value="{manifest_json}">
        <button type="submit">Create GitHub App</button>
      </form>
    </body></html>
    """


def _update_env(values: dict[str, str]) -> None:
    text = ENV_PATH.read_text(encoding="utf-8")
    for key, value in values.items():
        if "\n" in value:
            escaped = value.replace('"', '\\"')
            replacement = f'{key}="{escaped}"'
        else:
            replacement = f"{key}={value}"
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, replacement.replace("\\", "\\\\"), text, count=1, flags=re.MULTILINE)
        else:
            text += f"\n{replacement}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


@router.get("/github/manifest-callback", response_class=HTMLResponse)
def github_manifest_callback(code: str = Query(...)) -> str:
    resp = httpx.post(f"https://api.github.com/app-manifests/{code}/conversions", timeout=30.0)
    resp.raise_for_status()
    data = resp.json()

    _update_env(
        {
            "GITHUB_APP_ID": str(data["id"]),
            "GITHUB_APP_SLUG": data["slug"],
            "GITHUB_APP_CLIENT_ID": data["client_id"],
            "GITHUB_APP_CLIENT_SECRET": data["client_secret"],
            "GITHUB_WEBHOOK_SECRET": data["webhook_secret"],
            "GITHUB_APP_PRIVATE_KEY": data["pem"],
        }
    )

    return f"""
    <html><body>
      <h3>GitHub App "{data['name']}" created and saved to .env</h3>
      <p>App ID: {data['id']} — slug: {data['slug']}</p>
      <p>Next: install the app on your test org/repos, then use its
      installation URL to test the connect flow.</p>
      <p><a href="{data['html_url']}/installations/new">Install this app now</a></p>
    </body></html>
    """
