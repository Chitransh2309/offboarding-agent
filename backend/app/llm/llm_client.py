"""Thin wrapper around an OpenAI-compatible chat completions endpoint.
Every caller in this package goes through invoke() so there is exactly one
place that talks to the LLM — narration, skill tagging, reassignment
justification all share it. The endpoint here happens to be Bedrock behind
an OpenAI-compatible gateway, but nothing in this module is Bedrock- or
provider-specific — swapping providers only means changing .env."""

from __future__ import annotations

import uuid

import httpx

from app.config import get_settings


def _log_invocation(
    purpose: str,
    system_prompt: str,
    user_prompt: str,
    response: str | None,
    error_message: str | None,
    organization_id: uuid.UUID | None,
    run_id: uuid.UUID | None,
) -> None:
    # Logging must never be why an LLM call fails or blocks its caller —
    # any error here (DB down, migration not yet applied, etc.) is
    # swallowed, not raised.
    try:
        from app.database import SessionLocal
        from app.models import LLMInvocation

        db = SessionLocal()
        try:
            db.add(
                LLMInvocation(
                    organization_id=organization_id,
                    run_id=run_id,
                    purpose=purpose,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response=response,
                    error_message=error_message,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


def invoke(
    system_prompt: str,
    user_prompt: str,
    purpose: str,
    max_tokens: int = 1024,
    organization_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
) -> str:
    settings = get_settings()

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    if settings.openai_project_id:
        headers["OpenAI-Project"] = settings.openai_project_id

    body = {
        "model": settings.openai_model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        with httpx.Client(base_url=settings.openai_base_url, headers=headers, timeout=60.0) as client:
            resp = client.post("/chat/completions", json=body)
            resp.raise_for_status()
            payload = resp.json()

        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if content is None:
            # This model spends tokens on an internal "reasoning" field before
            # writing content — a too-small max_tokens truncates it before any
            # content is produced (finish_reason "length" with content still
            # null). Fail loudly rather than returning None and letting it
            # crash downstream as a confusing TypeError.
            raise RuntimeError(
                f"LLM returned no content (finish_reason={choice.get('finish_reason')!r}); "
                f"max_tokens={max_tokens} was likely too small for this model's reasoning overhead"
            )
    except Exception as exc:
        _log_invocation(purpose, system_prompt, user_prompt, None, str(exc), organization_id, run_id)
        raise

    _log_invocation(purpose, system_prompt, user_prompt, content, None, organization_id, run_id)
    return content
