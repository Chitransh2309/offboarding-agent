from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, employees, integrations, offboarding, reassignments, webhooks
from app.config import get_settings

app = FastAPI(title="Offboarding Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(integrations.router)
app.include_router(employees.router)
app.include_router(offboarding.router)
app.include_router(reassignments.router)
app.include_router(webhooks.router)

if get_settings().environment == "development":
    from app.api import dev_setup

    app.include_router(dev_setup.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
