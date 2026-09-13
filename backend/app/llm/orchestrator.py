"""The LLM's role is narration and disambiguation over a pre-filtered
slice — never the safety-critical decision of whether to revoke/verify.
Callers must scope inputs to one employee (or a small candidate set)
before reaching this module; it never receives a full-organization dump."""

from __future__ import annotations

from app.llm.llm_client import invoke
from app.models import AccessGrant, Employee, WorkItem

_NARRATE_SYSTEM_PROMPT = """You are narrating an employee offboarding run for \
an IT admin. Given the employee's access grants and open work items, write \
a short, factual plan summary (3-6 sentences): what will be revoked, and \
what open work needs reassignment. Do not invent access or tasks not \
listed. Do not claim anything has been revoked yet — this is the plan, \
not the result."""

_DISAMBIGUATE_SYSTEM_PROMPT = """You are matching a free-text employee search \
query to the correct candidate. Return ONLY the employee_id (a UUID) of the \
best match from the candidate list, or the literal word "NONE" if no \
candidate is a confident match. Never guess when there are multiple \
equally plausible candidates and the query doesn't disambiguate them \
— return NONE instead."""


def narrate_offboarding_plan(
    employee: Employee, access_grants: list[AccessGrant], work_items: list[WorkItem]
) -> str:
    grants_text = "\n".join(
        f"- {g.system.value}: {g.grant_type} on {g.resource_name or g.external_id} ({g.role or 'no role'})"
        for g in access_grants
    ) or "(none)"
    items_text = "\n".join(
        f"- {w.system.value} {w.item_type}: {w.title or w.external_id} [{w.status.value}]"
        for w in work_items
    ) or "(none)"

    user_prompt = (
        f"Employee: {employee.full_name} ({employee.company_email}), {employee.department or 'no department'}\n\n"
        f"Active access grants:\n{grants_text}\n\n"
        f"Open work items:\n{items_text}"
    )
    return invoke(
        _NARRATE_SYSTEM_PROMPT,
        user_prompt,
        purpose="narrate_offboarding_plan",
        max_tokens=1024,
        organization_id=employee.organization_id,
    )


def disambiguate_employee(candidates: list[Employee], query: str) -> Employee | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    candidates_text = "\n".join(
        f"- id={c.id} name={c.full_name} email={c.company_email} dept={c.department or 'n/a'}"
        for c in candidates
    )
    user_prompt = f"Query: {query!r}\n\nCandidates:\n{candidates_text}\n\nBest match employee_id:"
    result = invoke(
        _DISAMBIGUATE_SYSTEM_PROMPT,
        user_prompt,
        purpose="disambiguate_employee",
        max_tokens=400,
        organization_id=candidates[0].organization_id,
    ).strip()
    if result == "NONE":
        return None
    for candidate in candidates:
        if str(candidate.id) == result:
            return candidate
    return None
