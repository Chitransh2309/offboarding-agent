from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAdmin, get_current_admin, get_db
from app.models import AccessGrant, Employee, IntegrationConnection, WorkItem
from app.models.enums import GrantStatus, WorkItemStatus
from app.schemas.employees import EmployeeDetailOut, EmployeeOut, ResyncResultOut, SystemResyncResult
from app.services.sync_service import discover_and_sync_connection

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> list[Employee]:
    return db.query(Employee).filter(Employee.organization_id == admin.organization_id).all()


@router.get("/{employee_id}", response_model=EmployeeDetailOut)
def get_employee(
    employee_id: UUID, db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> Employee:
    """The targeted memory-layer read: this employee's identities/access/
    work only — never a full-organization scan."""
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.organization_id == admin.organization_id)
        .first()
    )
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")

    employee.access_grants = (
        db.query(AccessGrant)
        .filter(AccessGrant.employee_id == employee_id, AccessGrant.status == GrantStatus.ACTIVE)
        .all()
    )
    employee.work_items = (
        db.query(WorkItem)
        .filter(WorkItem.employee_id == employee_id, WorkItem.status != WorkItemStatus.CLOSED)
        .all()
    )
    return employee


@router.post("/resync", response_model=ResyncResultOut)
def resync_employees(
    db: Session = Depends(get_db), admin: CurrentAdmin = Depends(get_current_admin)
) -> ResyncResultOut:
    """Re-runs discover_and_sync_connection for every connection belonging
    to THIS admin's organization only — never other orgs' connections."""
    connections = (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.organization_id == admin.organization_id)
        .all()
    )
    results = [
        SystemResyncResult(system=connection.system, **discover_and_sync_connection(db, connection))
        for connection in connections
    ]
    return ResyncResultOut(results=results)
