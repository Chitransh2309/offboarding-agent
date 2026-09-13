"""The safety-critical module. revoke_and_verify() and reassign_and_verify()
are plain functions, not tools an LLM assembles at runtime — the model
decides WHICH grants/items to act on (upstream) and proposes WHO to
reassign to, but never whether verification happens. Every call here always
re-checks live state, acts, verifies, and writes the result row — no code
path skips the verify step. See Implementation_Plan.pdf, "Architecture
Overview" and "execution_service.py — the safety-critical module"."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.base import get_client
from app.models import (
    AccessGrant,
    Employee,
    IntegrationConnection,
    OffboardingRun,
    ReassignmentAction,
    RevocationAction,
    WorkItem,
)
from app.models.enums import ActionStatus, EnvironmentType, GrantStatus, RunStatus, VerifyStatus
from app.services.identity_resolution_service import get_identity


class ReassignmentNotConfirmedError(RuntimeError):
    """Raised if reassign_and_verify is called before a human has set
    confirmed_owner_id — this is the only gate in this module, and it is
    enforced here, not left to callers to remember."""


def _connection_for(db: Session, organization_id: uuid.UUID, system, environment: EnvironmentType) -> IntegrationConnection:
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.system == system,
            IntegrationConnection.environment == environment,
        )
        .first()
    )
    if connection is None:
        raise RuntimeError(f"no active {system} connection for organization {organization_id} ({environment})")
    return connection


def revoke_and_verify(db: Session, run: OffboardingRun, grant: AccessGrant) -> RevocationAction:
    action = RevocationAction(run_id=run.id, access_grant_id=grant.id)
    db.add(action)
    db.flush()

    connection = _connection_for(db, run.organization_id, grant.system, run.environment)
    client = get_client(connection)

    identity = get_identity(db, grant.employee_id, grant.system)
    employee_external_id = identity.external_id if identity else ""
    employee_external_handle = identity.external_handle if identity else None

    # Live targeted re-check: don't trust the memory-layer cache at the
    # moment it matters. If it's already gone, there's nothing to revoke.
    already_absent = client.verify_revoked(grant, employee_external_id, employee_external_handle)

    action.revoke_attempted_at = datetime.now(timezone.utc)
    if already_absent:
        action.revoke_status = ActionStatus.SUCCESS
        action.raw_response = {"note": "already absent on live re-check, revoke call skipped"}
    else:
        result = client.revoke(grant, employee_external_id, employee_external_handle)
        action.revoke_status = ActionStatus.SUCCESS if result.success else ActionStatus.FAILED
        action.raw_response = result.raw_response
        action.error_message = result.error_message

    # Unconditional verify — runs regardless of whether revoke_status above
    # was success or failed.
    verified_absent = client.verify_revoked(grant, employee_external_id, employee_external_handle)
    action.verified_at = datetime.now(timezone.utc)
    action.verify_status = VerifyStatus.VERIFIED if verified_absent else VerifyStatus.STILL_PRESENT

    grant.status = GrantStatus.REVOKED if verified_absent else GrantStatus.REVOKE_FAILED
    grant.last_verified_at = action.verified_at

    db.commit()
    db.refresh(action)
    return action


def reassign_and_verify(db: Session, run: OffboardingRun, reassignment: ReassignmentAction) -> ReassignmentAction:
    if reassignment.confirmed_owner_id is None:
        raise ReassignmentNotConfirmedError(
            f"reassignment_actions.id={reassignment.id} has no confirmed_owner_id; "
            "a human must confirm before this can execute"
        )

    work_item = db.get(WorkItem, reassignment.work_item_id)
    if work_item is None:
        raise RuntimeError(f"work_item {reassignment.work_item_id} not found")

    connection = _connection_for(db, run.organization_id, work_item.system, run.environment)
    client = get_client(connection)

    new_owner_identity = get_identity(db, reassignment.confirmed_owner_id, work_item.system)
    if new_owner_identity is None:
        reassignment.reassign_status = ActionStatus.FAILED
        reassignment.error_message = (
            f"confirmed owner has no {work_item.system.value} identity — cannot reassign"
        )
        reassignment.reassign_attempted_at = datetime.now(timezone.utc)
        reassignment.verify_status = VerifyStatus.ERROR
        reassignment.verified_at = reassignment.reassign_attempted_at
        db.commit()
        db.refresh(reassignment)
        return reassignment

    reassignment.reassign_attempted_at = datetime.now(timezone.utc)
    result = client.reassign(work_item, new_owner_identity.external_id)
    reassignment.reassign_status = ActionStatus.SUCCESS if result.success else ActionStatus.FAILED
    reassignment.raw_response = result.raw_response
    reassignment.error_message = result.error_message

    # Unconditional verify, same as revoke_and_verify — never skipped.
    verified = client.verify_reassigned(work_item, new_owner_identity.external_id)
    reassignment.verified_at = datetime.now(timezone.utc)
    reassignment.verify_status = VerifyStatus.VERIFIED if verified else VerifyStatus.STILL_PRESENT

    if verified:
        work_item.employee_id = reassignment.confirmed_owner_id

    db.commit()
    db.refresh(reassignment)
    return reassignment


def start_offboarding_run(
    db: Session, organization_id: uuid.UUID, employee_id: uuid.UUID, initiated_by: str, environment: EnvironmentType
) -> OffboardingRun:
    """Creates the run and executes revoke_and_verify for every active
    access_grant immediately. Reassignment is deliberately NOT executed here
    — reassignment_actions rows are created with a suggested_owner_id for
    the UI to show, but reassign_and_verify only runs after a human calls
    the confirm endpoint. In production this loop would run as a background
    task/queue rather than inline in the request; kept inline here for a
    structurally complete, easy-to-follow reference implementation."""
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise RuntimeError(f"employee {employee_id} not found")

    run = OffboardingRun(
        organization_id=organization_id,
        employee_id=employee_id,
        initiated_by=initiated_by,
        environment=environment,
        status=RunStatus.IN_PROGRESS,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    active_grants = (
        db.query(AccessGrant)
        .filter(AccessGrant.employee_id == employee_id, AccessGrant.status == GrantStatus.ACTIVE)
        .all()
    )

    any_failed = False
    for grant in active_grants:
        try:
            action = revoke_and_verify(db, run, grant)
            if action.verify_status != VerifyStatus.VERIFIED:
                any_failed = True
        except Exception:
            any_failed = True

    run.status = RunStatus.COMPLETED_WITH_ERRORS if any_failed else RunStatus.COMPLETED
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
