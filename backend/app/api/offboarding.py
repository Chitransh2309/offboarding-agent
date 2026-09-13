from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAdmin, get_current_admin, get_db
from app.llm.orchestrator import narrate_offboarding_plan
from app.llm.reassignment_suggester import suggest_reassignment_owner
from app.models import AccessGrant, Employee, OffboardingRun, ReassignmentAction, RevocationAction, WorkItem
from app.models.enums import GrantStatus, SuggestedBy, WorkItemStatus
from app.schemas.offboarding import OffboardingRunDetailOut, OffboardingRunOut, StartRunRequest
from app.services.execution_service import start_offboarding_run
from app.services.reporting_service import write_offboarding_report

router = APIRouter(prefix="/offboarding", tags=["offboarding"])


@router.post("/runs", response_model=OffboardingRunDetailOut, status_code=status.HTTP_201_CREATED)
def start_run(
    body: StartRunRequest, db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> dict:
    employee = (
        db.query(Employee)
        .filter(Employee.id == body.employee_id, Employee.organization_id == admin.organization_id)
        .first()
    )
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")

    # Narrate the plan from the pre-filtered slice for this one employee
    # BEFORE execution — the model explains what will happen, it doesn't
    # decide whether revoke/verify runs.
    active_grants = (
        db.query(AccessGrant)
        .filter(AccessGrant.employee_id == employee.id, AccessGrant.status == GrantStatus.ACTIVE)
        .all()
    )
    open_items = (
        db.query(WorkItem)
        .filter(WorkItem.employee_id == employee.id, WorkItem.status != WorkItemStatus.CLOSED)
        .all()
    )
    try:
        narrative = narrate_offboarding_plan(employee, active_grants, open_items)
    except Exception:
        narrative = None  # Bedrock unavailable — narration is best-effort, never blocks the run.

    run = start_offboarding_run(
        db,
        organization_id=admin.organization_id,
        employee_id=employee.id,
        initiated_by=admin.email,
        environment=body.environment,
    )

    # Reassignment suggestions are created here but NOT executed — only a
    # human confirming via POST /reassignments/{id}/confirm triggers
    # reassign_and_verify.
    for item in open_items:
        suggested, justification = suggest_reassignment_owner(db, item, employee, run_id=run.id)
        db.add(
            ReassignmentAction(
                run_id=run.id,
                work_item_id=item.id,
                suggested_owner_id=suggested.id if suggested else None,
                suggested_by=SuggestedBy.LLM,
                justification=justification,
            )
        )
    db.commit()

    # Best-effort, automatic — never blocks or fails the run itself. Skips
    # silently if the org hasn't configured a Notion reports parent page.
    notion_report_url = write_offboarding_report(db, run, employee, narrative)

    revocation_actions = db.query(RevocationAction).filter(RevocationAction.run_id == run.id).all()
    return {
        **OffboardingRunOut.model_validate(run).model_dump(),
        "revocation_actions": revocation_actions,
        "narrative": narrative,
        "notion_report_url": notion_report_url,
    }


@router.get("/runs/{run_id}", response_model=OffboardingRunDetailOut)
def get_run(
    run_id: UUID, db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> dict:
    run = (
        db.query(OffboardingRun)
        .filter(OffboardingRun.id == run_id, OffboardingRun.organization_id == admin.organization_id)
        .first()
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")

    revocation_actions = db.query(RevocationAction).filter(RevocationAction.run_id == run.id).all()
    return {**OffboardingRunOut.model_validate(run).model_dump(), "revocation_actions": revocation_actions, "narrative": None}
