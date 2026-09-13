"""Daily cron job. Tags new/changed work_items via the LLM, then
recomputes employee_skill_profile for every employee whose work_items
changed — scoped per employee, not a full-org recompute. This write path
is left ungated (no human confirmation) because mistagging only makes a
reassignment suggestion slightly worse; it never grants access or loses
work. See Implementation_Plan.pdf, Phase 4."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.llm.skill_tagger import infer_skill_tags
from app.models import EmployeeSkillProfile, WorkItem


def _skill_catalog(db: Session) -> list[str]:
    rows = db.query(WorkItem.skill_tags).filter(WorkItem.skill_tags.isnot(None)).all()
    catalog: set[str] = set()
    for (tags,) in rows:
        catalog.update(tags or [])
    return sorted(catalog)


def tag_pending_work_items(db: Session, employee_id: uuid.UUID | None = None) -> set[uuid.UUID]:
    """employee_id scopes this to one employee's pending items — used right
    after a sync/resync touches that employee, so tags fill in immediately
    instead of waiting for the next daily cron pass. Left unscoped (None)
    for the cron's full-table sweep."""
    query = db.query(WorkItem).filter(
        or_(
            WorkItem.skill_tags.is_(None),
            WorkItem.skill_tagged_at.is_(None),
            WorkItem.skill_tagged_at < WorkItem.last_synced_at,
        )
    )
    if employee_id is not None:
        query = query.filter(WorkItem.employee_id == employee_id)
    pending = query.all()

    affected_employee_ids: set[uuid.UUID] = set()
    if not pending:
        return affected_employee_ids

    catalog = _skill_catalog(db)
    for item in pending:
        try:
            tags = infer_skill_tags(
                title=item.title or "",
                description=None,
                item_type=item.item_type,
                existing_catalog=catalog,
                organization_id=item.organization_id,
            )
        except Exception:
            # One item's LLM call failing (rate limit, transient error, a
            # reasoning-model response that still didn't fit max_tokens)
            # shouldn't kill the whole batch — it stays untagged and gets
            # retried on tomorrow's run since skill_tagged_at is left unset.
            continue
        item.skill_tags = tags or None
        item.skill_tagged_at = datetime.now(timezone.utc)
        affected_employee_ids.add(item.employee_id)
        catalog = sorted(set(catalog) | set(tags))

    db.commit()
    return affected_employee_ids


def recompute_skill_profile_for_employee(db: Session, employee_id: uuid.UUID) -> None:
    items = (
        db.query(WorkItem)
        .filter(WorkItem.employee_id == employee_id, WorkItem.skill_tags.isnot(None))
        .all()
    )

    counts: Counter[str] = Counter()
    last_active: dict[str, datetime] = {}
    for item in items:
        item_time = item.last_synced_at or item.created_at
        for tag in item.skill_tags or []:
            counts[tag] += 1
            if tag not in last_active or item_time > last_active[tag]:
                last_active[tag] = item_time

    db.query(EmployeeSkillProfile).filter(EmployeeSkillProfile.employee_id == employee_id).delete()

    now = datetime.now(timezone.utc)
    for tag, count in counts.items():
        db.add(
            EmployeeSkillProfile(
                employee_id=employee_id,
                skill_tag=tag,
                task_count=count,
                last_active_at=last_active.get(tag),
                updated_at=now,
            )
        )
    db.commit()


def run_daily_skill_tagging(db: Session) -> None:
    affected_employee_ids = tag_pending_work_items(db)
    for employee_id in affected_employee_ids:
        recompute_skill_profile_for_employee(db, employee_id)
