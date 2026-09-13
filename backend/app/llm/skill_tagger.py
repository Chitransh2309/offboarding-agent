"""infer_skill_tags — the one LLM write path left ungated, per design: a
mistagged skill only makes a reassignment suggestion slightly worse, it
never grants access or loses work, so it doesn't need human confirmation
the way revoke/reassign do."""

from __future__ import annotations

import json
import uuid

from app.llm.llm_client import invoke

_SYSTEM_PROMPT = """You tag software work items (issues, pull requests, pages) \
with short skill/domain tags describing what the task involves. Prefer an \
existing tag from the provided catalog over minting a near-duplicate \
(e.g. reuse "payments" rather than inventing "payment-processing"). Only \
add a new tag if nothing in the catalog fits. Return 1-4 tags.

Respond with ONLY a JSON array of lowercase strings, nothing else. \
Example: ["payments", "idempotency"]"""


def infer_skill_tags(
    title: str,
    description: str | None,
    item_type: str,
    existing_catalog: list[str],
    organization_id: uuid.UUID | None = None,
) -> list[str]:
    catalog_text = ", ".join(sorted(existing_catalog)) if existing_catalog else "(none yet)"
    user_prompt = (
        f"Existing tag catalog: {catalog_text}\n\n"
        f"Item type: {item_type}\n"
        f"Title: {title}\n"
        f"Description: {description or '(none)'}\n\n"
        "Tags:"
    )
    raw = invoke(
        _SYSTEM_PROMPT, user_prompt, purpose="skill_tagging", max_tokens=500, organization_id=organization_id
    )
    try:
        tags = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(tags, list):
        return []
    return [str(tag).strip().lower() for tag in tags if str(tag).strip()]
