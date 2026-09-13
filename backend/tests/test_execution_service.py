"""Proves the guarantees execution_service.py is supposed to give:
verify_revoked/verify_reassigned always run regardless of the action's own
success flag, and reassign_and_verify refuses to run without a
human-confirmed owner. These are the properties the whole "keep the LLM
out of the revoke/verify decision path" design depends on."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.base import ActionResult
from app.models import AccessGrant, OffboardingRun, ReassignmentAction, WorkItem
from app.models.enums import EnvironmentType, GrantStatus, SystemType, VerifyStatus, WorkItemStatus
from app.services.execution_service import (
    ReassignmentNotConfirmedError,
    reassign_and_verify,
    revoke_and_verify,
)


def _grant() -> AccessGrant:
    return AccessGrant(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        system=SystemType.GITHUB,
        grant_type="org_member",
        external_id="acme-demo",
        status=GrantStatus.ACTIVE,
    )


def _run() -> OffboardingRun:
    return OffboardingRun(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        initiated_by="test",
        environment=EnvironmentType.SANDBOX,
    )


@patch("app.services.execution_service.get_identity")
@patch("app.services.execution_service._connection_for")
@patch("app.services.execution_service.get_client")
def test_verify_always_runs_even_when_revoke_fails(mock_get_client, mock_conn, mock_identity, mock_db):
    client = MagicMock()
    client.verify_revoked.side_effect = [False, False]  # not absent before, still present after
    client.revoke.return_value = ActionResult(success=False, error_message="API error")
    mock_get_client.return_value = client
    mock_identity.return_value = None

    grant = _grant()
    run = _run()

    action = revoke_and_verify(mock_db, run, grant)

    assert client.revoke.called
    assert client.verify_revoked.call_count == 2  # pre-check AND unconditional post-check
    assert action.verify_status == VerifyStatus.STILL_PRESENT
    assert grant.status == GrantStatus.REVOKE_FAILED


@patch("app.services.execution_service.get_identity")
@patch("app.services.execution_service._connection_for")
@patch("app.services.execution_service.get_client")
def test_verify_catches_revoke_that_lies_about_success(mock_get_client, mock_conn, mock_identity, mock_db):
    """A revoke call can report success=True while the grant is still
    actually present (e.g. eventual consistency, wrong resource). The
    unconditional verify step must be what determines ground truth, not
    the action's own success flag."""
    client = MagicMock()
    client.verify_revoked.side_effect = [False, False]
    client.revoke.return_value = ActionResult(success=True)  # claims success
    mock_get_client.return_value = client
    mock_identity.return_value = None

    action = revoke_and_verify(mock_db, _run(), _grant())

    assert action.revoke_status.value == "success"
    assert action.verify_status == VerifyStatus.STILL_PRESENT  # verify overrides the claim


@patch("app.services.execution_service.get_identity")
@patch("app.services.execution_service._connection_for")
@patch("app.services.execution_service.get_client")
def test_revoke_skipped_when_already_absent_on_live_recheck(mock_get_client, mock_conn, mock_identity, mock_db):
    client = MagicMock()
    client.verify_revoked.side_effect = [True, True]  # already absent before acting
    mock_get_client.return_value = client
    mock_identity.return_value = None

    action = revoke_and_verify(mock_db, _run(), _grant())

    assert not client.revoke.called  # nothing to revoke
    assert action.verify_status == VerifyStatus.VERIFIED


def test_reassign_requires_confirmed_owner(mock_db):
    reassignment = ReassignmentAction(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        work_item_id=uuid.uuid4(),
        confirmed_owner_id=None,
    )

    with pytest.raises(ReassignmentNotConfirmedError):
        reassign_and_verify(mock_db, _run(), reassignment)


@patch("app.services.execution_service.get_identity")
@patch("app.services.execution_service._connection_for")
@patch("app.services.execution_service.get_client")
def test_reassign_verify_always_runs(mock_get_client, mock_conn, mock_identity, mock_db):
    work_item = WorkItem(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        system=SystemType.LINEAR,
        item_type="issue",
        external_id="lin_1",
        status=WorkItemStatus.OPEN,
    )
    mock_db.get.return_value = work_item

    client = MagicMock()
    client.reassign.return_value = ActionResult(success=True)
    client.verify_reassigned.return_value = False  # claims success but verify disagrees
    mock_get_client.return_value = client
    mock_identity.return_value = MagicMock(external_id="new-owner-id")

    reassignment = ReassignmentAction(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        work_item_id=work_item.id,
        confirmed_owner_id=uuid.uuid4(),
    )

    result = reassign_and_verify(mock_db, _run(), reassignment)

    assert client.verify_reassigned.called
    assert result.verify_status == VerifyStatus.STILL_PRESENT
