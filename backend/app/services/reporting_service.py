"""Writes offboarding audit reports to Notion, automatically, right after
a run completes. Opt-in per org: skipped entirely if the admin hasn't
configured a Notion parent page to write under (integration_connections.
settings["notion_reports_parent_page_id"]). Failures here never propagate
to the caller — a report failing to write must not affect the actual
offboarding run's success/failure."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.base import get_client
from app.integrations.notion_client import NotionClient
from app.models import (
    AccessGrant,
    Employee,
    IntegrationConnection,
    OffboardingRun,
    ReassignmentAction,
    RevocationAction,
    WorkItem,
)
from app.models.enums import EnvironmentType, SystemType

REPORTS_PARENT_PAGE_KEY = "notion_reports_parent_page_id"


def write_offboarding_report(
    db: Session, run: OffboardingRun, employee: Employee, narrative: str | None
) -> str | None:
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.organization_id == run.organization_id,
            IntegrationConnection.system == SystemType.NOTION,
            IntegrationConnection.environment == EnvironmentType.PRODUCTION,
        )
        .first()
    )
    if connection is None or not connection.settings:
        return None

    parent_page_id = connection.settings.get(REPORTS_PARENT_PAGE_KEY)
    if not parent_page_id:
        return None

    revocations = db.query(RevocationAction).filter(RevocationAction.run_id == run.id).all()
    revoked_items: list[tuple[str, str, str]] = []
    for action in revocations:
        grant = db.get(AccessGrant, action.access_grant_id)
        if grant is None:
            continue
        revoked_items.append((grant.system.value, grant.resource_name or grant.external_id, action.verify_status.value))

    reassignments = db.query(ReassignmentAction).filter(ReassignmentAction.run_id == run.id).all()
    reassigned_items: list[tuple[str, str]] = []
    for action in reassignments:
        item = db.get(WorkItem, action.work_item_id)
        item_title = item.title if item and item.title else str(action.work_item_id)
        if action.confirmed_owner_id:
            owner = db.get(Employee, action.confirmed_owner_id)
            owner_label = f"{owner.full_name} (confirmed, {action.verify_status.value})" if owner else "confirmed"
        elif action.suggested_owner_id:
            owner = db.get(Employee, action.suggested_owner_id)
            owner_label = f"{owner.full_name} (suggested, pending confirmation)" if owner else "suggested"
        else:
            owner_label = "no candidate found — needs manual assignment"
        reassigned_items.append((item_title, owner_label))

    try:
        client = get_client(connection)
        assert isinstance(client, NotionClient)
        date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        page = client.create_report_page(
            parent_page_id=parent_page_id,
            title=f"Offboarding Report — {employee.full_name} ({date_label})",
            narrative=narrative,
            revoked_items=revoked_items,
            reassigned_items=reassigned_items,
        )
        return page.get("url")
    except Exception:
        # Best-effort — a report-writing failure must never look like the
        # offboarding run itself failed.
        return None
