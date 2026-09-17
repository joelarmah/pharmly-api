import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


def _generate_admin_user_id() -> str:
    return f"adm_{secrets.token_hex(12)}"


class AdminUser(Base):
    """Staff account for /admin (app/admin.py). Managed via
    scripts/manage_admin_users.py, not through the browsable admin UI --
    building a safe password-entry form inside a generic admin-UI library
    is its own risk, not worth taking on for an internal tool.
    """

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_admin_user_id)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Stored for future differentiated permissions; every account is a
    # full admin for now regardless of this value.
    role: Mapped[str] = mapped_column(String, nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
