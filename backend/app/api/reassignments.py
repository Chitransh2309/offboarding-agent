from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAdmin, get_current_admin, get_db
from app.models import Employee, OffboardingRun, ReassignmentAction
from app.schemas.reassignments import ConfirmReassignmentRequest, ReassignmentActionOut
from app.services.execution_service import ReassignmentNotConfirmedError, reassign_and_verify

router = APIRouter(prefix="/reassignments", tags=["reassignments"])


@router.get("/{run_id}", response_model=list[ReassignmentActionOut])
def list_reassignments(
    run_id: UUID, db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> list[ReassignmentAction]:
    run = (
        db.query(OffboardingRun)
        .filter(OffboardingRun.id == run_id, OffboardingRun.organization_id == admin.organization_id)
        .first()
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return db.query(ReassignmentAction).filter(ReassignmentAction.run_id == run_id).all()


@router.post("/{reassignment_id}/confirm", response_model=ReassignmentActionOut)
def confirm_reassignment(
    reassignment_id: UUID,
    body: ConfirmReassignmentRequest,
    db: Session = Depends(get_db),
    admin: CurrentAdmin = Depends(get_current_admin),
) -> ReassignmentAction:
    """Confirming is what gates execution: reassign_and_verify only ever
    runs after this call sets confirmed_owner_id — never automatically off
    the LLM's suggestion alone."""
    reassignment = db.get(ReassignmentAction, reassignment_id)
    if reassignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reassignment not found")

    run = db.get(OffboardingRun, reassignment.run_id)
    if run is None or run.organization_id != admin.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reassignment not found")

    new_owner = (
        db.query(Employee)
        .filter(Employee.id == body.confirmed_owner_id, Employee.organization_id == admin.organization_id)
        .first()
    )
    if new_owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "confirmed_owner_id is not a valid employee")

    reassignment.confirmed_owner_id = body.confirmed_owner_id
    db.commit()
    db.refresh(reassignment)

    try:
        return reassign_and_verify(db, run, reassignment)
    except ReassignmentNotConfirmedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
