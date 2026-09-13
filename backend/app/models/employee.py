import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPKMixin, pg_enum
from app.models.enums import EmployeeStatus


class Employee(Base, UUIDPKMixin):
    __tablename__ = "employees"
    __table_args__ = (sa.UniqueConstraint("organization_id", "company_email", name="uq_employee_org_email"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    company_email: Mapped[str] = mapped_column(sa.Text, nullable=False)
    department: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        pg_enum(EmployeeStatus, "employee_status"), nullable=False, default=EmployeeStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
