from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import decode_access_token

__all__ = ["get_db", "CurrentAdmin", "get_current_admin"]

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentAdmin:
    organization_id: UUID
    admin_id: UUID
    email: str


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentAdmin:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return CurrentAdmin(
        organization_id=UUID(payload["sub"]),
        admin_id=UUID(payload["admin_id"]),
        email=payload["email"],
    )
