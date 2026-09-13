"""Resolves a per-system account to an employees row, once, at sync time —
not re-derived by search on every offboarding run. See
docs/Implementation_Plan.pdf section on employee_identities."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import Employee, EmployeeIdentity
from app.models.enums import SystemType


def resolve_identity(
    db: Session,
    organization_id: uuid.UUID,
    system: SystemType,
    external_id: str,
    external_handle: str | None = None,
    email: str | None = None,
) -> Employee | None:
    """Returns the Employee this external account belongs to, creating the
    employee_identities link if a match is found by email but not yet
    linked. Returns None if no employee record matches — sync_service
    should log and skip rather than fabricate an employee."""

    existing_identity = (
        db.query(EmployeeIdentity)
        .filter(EmployeeIdentity.system == system, EmployeeIdentity.external_id == external_id)
        .first()
    )
    if existing_identity is not None:
        if external_handle and existing_identity.external_handle != external_handle:
            existing_identity.external_handle = external_handle
            db.commit()
        return db.get(Employee, existing_identity.employee_id)

    if not email:
        return None

    employee = (
        db.query(Employee)
        .filter(Employee.organization_id == organization_id, Employee.company_email == email)
        .first()
    )
    if employee is None:
        return None

    identity = EmployeeIdentity(
        employee_id=employee.id,
        system=system,
        external_id=external_id,
        external_handle=external_handle,
    )
    db.add(identity)
    db.commit()
    return employee


def resolve_or_create_employee(
    db: Session,
    organization_id: uuid.UUID,
    system: SystemType,
    external_id: str,
    external_handle: str | None,
    email: str | None,
) -> tuple[Employee | None, bool]:
    """Used by employee discovery (a whole workspace roster, not one known
    person). resolve_identity() only ever links to an employee that already
    exists; this creates a brand-new Employee when nothing matches — but
    only when we have an email, since that's the one identifier we trust
    enough to mint a new record from. Systems that don't expose email
    (GitHub) can attach an identity to an employee discovered elsewhere,
    but can never create one on their own — returns (None, False) in that
    case, and the caller should skip rather than fabricate a placeholder
    email. Returns (employee, was_created)."""

    employee = resolve_identity(db, organization_id, system, external_id, external_handle, email)
    if employee is not None:
        return employee, False

    if not email and external_handle:
        # Best-effort fallback for systems with no email (GitHub): if the
        # handle exactly matches the local-part of an existing employee's
        # email, link them. Not every org follows this convention, so this
        # only ever links to an employee that already exists — a wrong
        # guess just means a missed link, never a fabricated record.
        candidate = (
            db.query(Employee)
            .filter(
                Employee.organization_id == organization_id,
                Employee.company_email.ilike(f"{external_handle}@%"),
            )
            .first()
        )
        if candidate is not None:
            db.add(
                EmployeeIdentity(
                    employee_id=candidate.id,
                    system=system,
                    external_id=external_id,
                    external_handle=external_handle,
                )
            )
            db.commit()
            return candidate, False

    if not email:
        return None, False

    employee = Employee(
        organization_id=organization_id,
        full_name=external_handle or email.split("@")[0],
        company_email=email,
    )
    db.add(employee)
    db.flush()

    db.add(
        EmployeeIdentity(
            employee_id=employee.id,
            system=system,
            external_id=external_id,
            external_handle=external_handle,
        )
    )
    db.commit()
    return employee, True


def get_identity(db: Session, employee_id: uuid.UUID, system: SystemType) -> EmployeeIdentity | None:
    return (
        db.query(EmployeeIdentity)
        .filter(EmployeeIdentity.employee_id == employee_id, EmployeeIdentity.system == system)
        .first()
    )
