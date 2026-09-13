"""Seeds "Acme Demo Co" — 6 employees, 2 managers x 2 reports each — from
app/scripts/demo_data/acme_demo_org.json into the relational schema.
Insert order follows the FK dependency chain from
docs/Implementation_Plan.pdf: organization -> employees (manager_id
backfilled in a second pass, since the JSON only has manager_email) ->
employee_identities -> access_grants -> work_items.

Run with: python -m app.scripts.seed_demo_org
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from app.database import SessionLocal
from app.models import AccessGrant, Employee, EmployeeIdentity, OrgAdmin, Organization, WorkItem
from app.models.enums import EmployeeStatus, GrantStatus, SystemType, WorkItemStatus
from app.security import hash_password

DATA_PATH = Path(__file__).parent / "demo_data" / "acme_demo_org.json"
ADMIN_EMAIL = "admin@acme-demo.com"


def _get_or_create_organization(db, name: str) -> Organization:
    org = db.query(Organization).filter(Organization.name == name).first()
    if org is None:
        org = Organization(name=name)
        db.add(org)
        db.flush()
    return org


def _get_or_create_admin(db, org: Organization) -> tuple[OrgAdmin, str | None]:
    admin = db.query(OrgAdmin).filter(OrgAdmin.email == ADMIN_EMAIL).first()
    if admin is not None:
        return admin, None

    password = secrets.token_urlsafe(12)
    admin = OrgAdmin(organization_id=org.id, email=ADMIN_EMAIL, password_hash=hash_password(password))
    db.add(admin)
    db.flush()
    return admin, password


def seed() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        org = _get_or_create_organization(db, data["organization"])
        admin, generated_password = _get_or_create_admin(db, org)

        by_email: dict[str, Employee] = {}
        for emp_data in data["employees"]:
            employee = (
                db.query(Employee)
                .filter(Employee.organization_id == org.id, Employee.company_email == emp_data["company_email"])
                .first()
            )
            if employee is None:
                employee = Employee(
                    organization_id=org.id,
                    full_name=emp_data["full_name"],
                    company_email=emp_data["company_email"],
                    department=emp_data.get("department"),
                    status=EmployeeStatus(emp_data["status"]),
                )
                db.add(employee)
                db.flush()
            by_email[emp_data["company_email"]] = employee

        for emp_data in data["employees"]:
            manager_email = emp_data.get("manager_email")
            if manager_email:
                by_email[emp_data["company_email"]].manager_id = by_email[manager_email].id
        db.flush()

        for emp_data in data["employees"]:
            employee = by_email[emp_data["company_email"]]

            for system_name, identity_data in emp_data["identities"].items():
                system = SystemType(system_name)
                existing = (
                    db.query(EmployeeIdentity)
                    .filter(EmployeeIdentity.system == system, EmployeeIdentity.external_id == identity_data["external_id"])
                    .first()
                )
                if existing is None:
                    db.add(
                        EmployeeIdentity(
                            employee_id=employee.id,
                            system=system,
                            external_id=identity_data["external_id"],
                            external_handle=identity_data.get("external_handle"),
                        )
                    )

            for grant_data in emp_data["access_grants"]:
                system = SystemType(grant_data["system"])
                existing = (
                    db.query(AccessGrant)
                    .filter(
                        AccessGrant.employee_id == employee.id,
                        AccessGrant.system == system,
                        AccessGrant.grant_type == grant_data["grant_type"],
                        AccessGrant.external_id == grant_data["external_id"],
                    )
                    .first()
                )
                if existing is None:
                    db.add(
                        AccessGrant(
                            organization_id=org.id,
                            employee_id=employee.id,
                            system=system,
                            grant_type=grant_data["grant_type"],
                            external_id=grant_data["external_id"],
                            resource_name=grant_data.get("resource_name"),
                            role=grant_data.get("role"),
                            status=GrantStatus.ACTIVE,
                        )
                    )

            for item_data in emp_data["work_items"]:
                system = SystemType(item_data["system"])
                existing = (
                    db.query(WorkItem)
                    .filter(WorkItem.system == system, WorkItem.external_id == item_data["external_id"])
                    .first()
                )
                if existing is None:
                    db.add(
                        WorkItem(
                            organization_id=org.id,
                            employee_id=employee.id,
                            system=system,
                            item_type=item_data["item_type"],
                            external_id=item_data["external_id"],
                            title=item_data.get("title"),
                            url=item_data.get("url"),
                            status=WorkItemStatus(item_data["status"]),
                            skill_tags=item_data.get("skill_tags"),
                        )
                    )

        db.commit()

        print(f"Seeded organization: {org.name} ({org.id})")
        print(f"Employees: {len(by_email)}")
        if generated_password:
            print(f"Admin login: {ADMIN_EMAIL} / {generated_password}  (save this — not shown again)")
        else:
            print(f"Admin login: {ADMIN_EMAIL} (already existed, password unchanged)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
