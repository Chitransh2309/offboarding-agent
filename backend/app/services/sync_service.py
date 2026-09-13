"""Keeps the memory layer (access_grants/work_items) warm. Webhooks handle
near-real-time updates for GitHub/Linear; reconcile_organization() is the
cron-shaped safety net for all four systems, since webhook delivery is
never fully trusted alone (missed deliveries, under-scoped apps, bulk
changes that don't fire events) — see Implementation_Plan.pdf."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.base import get_client
from app.models import AccessGrant, Employee, IntegrationConnection, WorkItem
from app.models.enums import EnvironmentType, GrantStatus, SystemType, WorkItemStatus
from app.services.identity_resolution_service import get_identity, resolve_identity, resolve_or_create_employee
from app.services.skill_tagging_service import recompute_skill_profile_for_employee, tag_pending_work_items


def _active_connection(
    db: Session, organization_id: uuid.UUID, system: SystemType, environment: EnvironmentType
) -> IntegrationConnection | None:
    return (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.system == system,
            IntegrationConnection.environment == environment,
        )
        .first()
    )


def _upsert_access_grant(db: Session, organization_id: uuid.UUID, employee_id: uuid.UUID, system: SystemType, data) -> None:
    grant = (
        db.query(AccessGrant)
        .filter(
            AccessGrant.employee_id == employee_id,
            AccessGrant.system == system,
            AccessGrant.grant_type == data.grant_type,
            AccessGrant.external_id == data.external_id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if grant is None:
        grant = AccessGrant(
            organization_id=organization_id,
            employee_id=employee_id,
            system=system,
            grant_type=data.grant_type,
            external_id=data.external_id,
            resource_name=data.resource_name,
            role=data.role,
            status=GrantStatus.ACTIVE,
        )
        db.add(grant)
    else:
        grant.resource_name = data.resource_name
        grant.role = data.role
        if grant.status in (GrantStatus.REVOKED, GrantStatus.REVOKE_FAILED):
            # Live re-check found it still there. REVOKED means it reappeared
            # after being removed — a re-grant. REVOKE_FAILED means a past
            # revoke attempt didn't take (exactly what verify_status =
            # STILL_PRESENT already told us) — without this branch that grant
            # stays stuck at REVOKE_FAILED forever: invisible to the "active
            # grants" query every future offboarding run reads from, and to
            # the employee detail page's active-grants filter, even though
            # it's still genuinely present. Either way, a live rediscovery
            # is ground truth and overrides the stale status.
            grant.status = GrantStatus.ACTIVE
    grant.last_synced_at = now


def _upsert_work_item(db: Session, organization_id: uuid.UUID, employee_id: uuid.UUID, system: SystemType, data) -> None:
    item = (
        db.query(WorkItem)
        .filter(WorkItem.system == system, WorkItem.external_id == data.external_id)
        .first()
    )
    now = datetime.now(timezone.utc)
    if item is None:
        item = WorkItem(
            organization_id=organization_id,
            employee_id=employee_id,
            system=system,
            item_type=data.item_type,
            external_id=data.external_id,
            title=data.title,
            url=data.url,
            status=WorkItemStatus(data.status),
        )
        db.add(item)
    else:
        item.employee_id = employee_id
        item.title = data.title
        item.url = data.url
        item.status = WorkItemStatus(data.status)
    item.last_synced_at = now


def reconcile_employee(db: Session, employee: Employee, connection: IntegrationConnection, client=None) -> None:
    identity = get_identity(db, employee.id, connection.system)
    if identity is None:
        return

    if client is None:
        # Only built fresh here for callers (webhook handlers) that don't
        # already have one. discover_and_sync_connection passes its own
        # client through instead of rebuilding — see that function for why
        # this matters for performance, not just avoiding a bit of overhead.
        client = get_client(connection)

    for grant_data in client.list_access(identity.external_id, identity.external_handle):
        _upsert_access_grant(db, employee.organization_id, employee.id, connection.system, grant_data)

    for item_data in client.list_work_items(identity.external_id, identity.external_handle):
        _upsert_work_item(db, employee.organization_id, employee.id, connection.system, item_data)

    db.commit()

    # Tag whatever just came in (or changed) for this employee right away,
    # scoped to just them — cheap compared to the cron's full-table sweep,
    # and means skill tags are ready by the time a reassignment suggestion
    # is needed, not stale until tomorrow's cron run.
    try:
        if tag_pending_work_items(db, employee_id=employee.id):
            recompute_skill_profile_for_employee(db, employee.id)
    except Exception:
        # Best-effort, same as the cron path — a tagging failure must never
        # break the sync/resync it's riding along with.
        pass


def discover_and_sync_connection(db: Session, connection: IntegrationConnection) -> dict:
    """The 'connect an app, get your employees' flow: pulls the actual
    member/user roster from the workspace (not just enriching employees we
    already know about), creates or links each one, then syncs their
    access_grants/work_items in the same pass. Systems without email
    (GitHub) can only attach an identity to an employee discovered
    elsewhere — see resolve_or_create_employee's docstring for why."""
    client = get_client(connection)

    discovered = 0
    linked = 0
    skipped = 0

    for member in client.list_members():
        employee, was_created = resolve_or_create_employee(
            db,
            organization_id=connection.organization_id,
            system=connection.system,
            external_id=member.external_id,
            external_handle=member.external_handle,
            email=member.email,
        )
        if employee is None:
            skipped += 1
            continue

        discovered += 1 if was_created else 0
        linked += 0 if was_created else 1

        # Same client instance reused for every employee in this pass —
        # GitHubClient/SlackClient cache their expensive org-wide list
        # calls (repos, teams, channels) on the instance, so those only
        # happen once per connection, not once per employee. Rebuilding a
        # fresh client per employee (the old behavior) silently threw that
        # cache away every time and re-fetched everything from scratch.
        reconcile_employee(db, employee, connection, client=client)

    return {"discovered": discovered, "linked": linked, "skipped": skipped}


def reconcile_organization(db: Session, organization_id: uuid.UUID, environment: EnvironmentType) -> None:
    """The daily-cron entry point: walks every connected system for this
    org, discovering any new members and refreshing the memory layer for
    everyone else."""
    for system in SystemType:
        connection = _active_connection(db, organization_id, system, environment)
        if connection is None:
            continue
        discover_and_sync_connection(db, connection)


def handle_github_webhook(db: Session, environment: EnvironmentType, event_type: str, payload: dict) -> None:
    """Targeted, single-item update triggered by a GitHub webhook delivery
    — cheaper and faster than a full reconciliation, used alongside it.
    GitHub Apps have exactly one webhook config for the whole app, shared
    across every org that installs it — there's no organization_id in the
    request at all. Every event payload carries installation.id, which we
    match against integration_connections.external_ref to find out which
    org this event actually belongs to."""
    if event_type not in ("member", "organization", "team", "issues", "pull_request"):
        return

    installation = payload.get("installation")
    if not installation:
        return

    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.system == SystemType.GITHUB,
            IntegrationConnection.environment == environment,
            IntegrationConnection.external_ref == str(installation["id"]),
        )
        .first()
    )
    if connection is None:
        return

    actor = payload.get("member") or payload.get("membership", {}).get("user") or payload.get("assignee")
    if not actor:
        return

    employee = resolve_identity(
        db,
        organization_id=connection.organization_id,
        system=SystemType.GITHUB,
        external_id=str(actor["id"]),
        external_handle=actor.get("login"),
    )
    if employee is None:
        return

    reconcile_employee(db, employee, connection)


def handle_linear_webhook(db: Session, organization_id: uuid.UUID, environment: EnvironmentType, payload: dict) -> None:
    assignee = payload.get("data", {}).get("assignee")
    if not assignee:
        return

    employee = resolve_identity(
        db,
        organization_id=organization_id,
        system=SystemType.LINEAR,
        external_id=assignee["id"],
        external_handle=assignee.get("name"),
    )
    if employee is None:
        return

    connection = _active_connection(db, organization_id, SystemType.LINEAR, environment)
    if connection is None:
        return

    reconcile_employee(db, employee, connection)
