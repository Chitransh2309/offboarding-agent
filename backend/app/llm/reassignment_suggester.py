"""Proposes suggested_owner_id for a reassignment_actions row. The ranking
itself is deterministic (skill-tag overlap against employee_skill_profile,
an instant lookup rather than a live scan of years of work_items) —
only the human-readable justification shown in the UI goes through the
LLM. The suggestion is never auto-executed: reassign_and_verify requires
a human-confirmed owner regardless of what's suggested here."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.llm.llm_client import invoke
from app.models import Employee, EmployeeSkillProfile, WorkItem
from app.models.enums import EmployeeStatus

_JUSTIFICATION_SYSTEM_PROMPT = """Write one short sentence (under 25 words) \
explaining why this teammate is a good reassignment candidate for this \
work item, based only on the facts given. Be factual, not promotional."""


def suggest_reassignment_owner(
    db: Session, work_item: WorkItem, departing_employee: Employee, run_id: uuid.UUID | None = None
) -> tuple[Employee | None, str]:
    candidates = (
        db.query(Employee)
        .filter(
            Employee.organization_id == departing_employee.organization_id,
            Employee.id != departing_employee.id,
            Employee.status == EmployeeStatus.ACTIVE,
        )
        .all()
    )
    if not candidates:
        return None, "No active teammates available to reassign to."

    candidate_ids = [c.id for c in candidates]
    best_employee_id = None
    best_score = 0
    best_matched_tags: list[str] = []

    if work_item.skill_tags:
        rows = (
            db.query(
                EmployeeSkillProfile.employee_id,
                func.sum(EmployeeSkillProfile.task_count).label("score"),
            )
            .filter(
                EmployeeSkillProfile.employee_id.in_(candidate_ids),
                EmployeeSkillProfile.skill_tag.in_(work_item.skill_tags),
            )
            .group_by(EmployeeSkillProfile.employee_id)
            .order_by(func.sum(EmployeeSkillProfile.task_count).desc())
            .all()
        )
        if rows:
            best_employee_id, best_score = rows[0]
            best_matched_tags = (
                db.query(EmployeeSkillProfile.skill_tag)
                .filter(
                    EmployeeSkillProfile.employee_id == best_employee_id,
                    EmployeeSkillProfile.skill_tag.in_(work_item.skill_tags),
                )
                .all()
            )
            best_matched_tags = [t[0] for t in best_matched_tags]

    if best_employee_id is not None:
        suggested = next(c for c in candidates if c.id == best_employee_id)
        justification = _justify(suggested, work_item, best_matched_tags, best_score, run_id)
        return suggested, justification

    # No skill overlap at all — fall back to a same-manager teammate so the
    # suggestion is still someone with organizational context, not random.
    same_manager = [c for c in candidates if c.manager_id == departing_employee.manager_id]
    if same_manager:
        suggested = same_manager[0]
        return suggested, f"No skill-tag match found; suggested as a same-team fallback ({suggested.department or 'same team'})."

    return None, "No skill match or same-team teammate found — needs manual assignment."


def _justify(
    employee: Employee, work_item: WorkItem, matched_tags: list[str], score: int, run_id: uuid.UUID | None
) -> str:
    user_prompt = (
        f"Candidate: {employee.full_name}, {employee.department or 'no department'}\n"
        f"Work item: {work_item.title or work_item.external_id} ({work_item.item_type})\n"
        f"Matched skill tags: {', '.join(matched_tags) or 'none'}\n"
        f"Candidate's historical task count on these tags: {score}"
    )
    try:
        return invoke(
            _JUSTIFICATION_SYSTEM_PROMPT,
            user_prompt,
            purpose="reassignment_justification",
            max_tokens=400,
            organization_id=employee.organization_id,
            run_id=run_id,
        ).strip()
    except Exception:
        # Justification text is a nice-to-have for the UI; never block the
        # suggestion itself on a Bedrock call failing.
        return f"Matched on skill tags: {', '.join(matched_tags) or 'none'} (task count {score})."
