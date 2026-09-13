from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import OrgAdmin, Organization
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(OrgAdmin).filter(OrgAdmin.email == body.admin_email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "an admin with this email already exists")

    org = Organization(name=body.organization_name)
    db.add(org)
    db.flush()  # assigns org.id without committing yet

    admin = OrgAdmin(
        organization_id=org.id,
        email=body.admin_email,
        password_hash=hash_password(body.admin_password),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    token = create_access_token(organization_id=org.id, admin_id=admin.id, admin_email=admin.email)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    admin = db.query(OrgAdmin).filter(OrgAdmin.email == body.email).first()
    if admin is None or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    token = create_access_token(
        organization_id=admin.organization_id, admin_id=admin.id, admin_email=admin.email
    )
    return TokenResponse(access_token=token)
