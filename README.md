# Offboarding Agent

Automated employee offboarding: sweeps external systems for a departing
employee's access footprint, revokes it, reassigns their open work, and
re-verifies each revocation actually took effect.

## Status

Project scaffolding only — architecture and integration design are being
worked out before implementation starts.

## Planned stack

- **Backend**: Python, FastAPI
- **Frontend**: Next.js, TypeScript
- **LLM**: AWS Bedrock
- **Integrations**: GitHub, Slack, Notion, Linear

## Layout

```
backend/    FastAPI service (integrations, LLM orchestration, audit logging)
frontend/   Next.js app (trigger UI + audit results)
```
