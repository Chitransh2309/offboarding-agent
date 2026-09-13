# Offboarding Agent

Automated employee offboarding: sweeps external systems (GitHub, Slack,
Notion, Linear) for a departing employee's access footprint, revokes it,
reassigns their open work to a teammate, and re-verifies each revocation
actually took effect before the run is reported complete.

**Live app:** https://offboardingagent.vercel.app/

## Status

Backend is implemented end-to-end (models, migrations, auth, integration
clients, execution/sync/skill-tagging services, API routers, tests).
Frontend covers auth, integration connect flows, the employee directory,
and the offboarding trigger + audit UI. See `docs/Implementation_Plan.pdf`
for the design this was built from.

## Architecture

```
Frontend (Next.js)
        |
        v
Backend (FastAPI)
  sync -> identity resolution -> execution service (revoke/reassign + verify)
                                        |
                                        v
                          LLM orchestrator (narration,
                     disambiguation, reassignment justification,
                              skill tagging)
        |
        v
External systems: GitHub, Slack, Notion, Linear
```

Each offboarding run follows the same loop for every access grant: **check
live state → act → re-verify live state → record the result.** Nothing is
marked revoked or reassigned because an API call returned 200 — it's marked
that way because a follow-up read confirms the access is actually gone (see
`execution_service.py`, the safety-critical module).

### Where the agent fits in

The LLM is deliberately kept out of the safety-critical path — it never
decides *whether* a revocation happened or *whether* verification is
skipped, and reassignments always require a human-confirmed owner before
`reassign_and_verify` will execute. Instead, the agent is scoped to the
judgment calls around that deterministic core:

- **Plan narration** — turns an employee's live access grants and open
  work items into a short, factual summary of what a run is about to do.
- **Employee disambiguation** — resolves a free-text search query to the
  correct employee record, or explicitly declines when candidates are
  ambiguous rather than guessing.
- **Reassignment suggestions** — work-item owner candidates are ranked
  deterministically (skill-tag overlap against historical task counts);
  the LLM only writes the human-readable justification for why a
  candidate was suggested.
- **Skill tagging** — a background job that tags work items with skill
  labels so the reassignment ranking above has something to match on.

Every LLM call is scoped to a single employee (or a small candidate set),
never a full-organization dump, and every invocation is logged
(`llm_invocation`) for audit.

## Stack

- **Backend**: Python, FastAPI, SQLAlchemy, Alembic, Postgres
- **Frontend**: Next.js, TypeScript
- **LLM**: AWS Bedrock
- **Integrations**: GitHub, Slack, Notion, Linear

## Layout

```
backend/    FastAPI service (integrations, LLM orchestration, audit logging)
frontend/   Next.js app (trigger UI + audit results)
```

## Backend quickstart

```
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
# fill in .env with your own DB/AWS/OAuth credentials — see .env.example
alembic upgrade head
python -m app.scripts.seed_demo_org      # optional: seeds "Acme Demo Co"
uvicorn app.main:app --reload
```

Cron-shaped jobs (webhook reconciliation safety net + daily skill tagging)
run via `python -m app.scripts.run_cron_jobs`, meant to be scheduled
externally rather than run inside the API process.
