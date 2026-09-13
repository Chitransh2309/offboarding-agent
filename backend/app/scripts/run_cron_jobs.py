"""The daily-cron entry point referenced throughout Implementation_Plan.pdf
(sync_service's reconciliation safety net + skill_tagging_service). Meant
to be invoked by an external scheduler (cron, Windows Task Scheduler,
Cloud Scheduler) once a day, not run inside the API process.

Run with: python -m app.scripts.run_cron_jobs
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models import IntegrationConnection, Organization
from app.services.skill_tagging_service import run_daily_skill_tagging
from app.services.sync_service import reconcile_organization


def run() -> None:
    db = SessionLocal()
    try:
        organizations = db.query(Organization).all()
        for org in organizations:
            environments = (
                db.query(IntegrationConnection.environment)
                .filter(IntegrationConnection.organization_id == org.id)
                .distinct()
                .all()
            )
            for (environment,) in environments:
                print(f"Reconciling {org.name} ({environment.value})...")
                reconcile_organization(db, org.id, environment)

        print("Running skill tagging...")
        run_daily_skill_tagging(db)
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
