from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.security import verify_password
from app.core.time import utcnow
from app.models.admin_user import AdminUser
from app.models.pharmacy import MedicationCatalog, Pharmacy, PharmacyPrice
from app.models.prescription import Medication, Prescription
from app.models.user import User

# Set by setup_admin() once the Admin instance exists. AdminAuth reads this
# (rather than a module it owns itself) so that repointing
# admin_instance.session_maker at a test database -- see tests/conftest.py --
# also covers login/session checks, not just the ModelView CRUD routes.
admin_instance: Admin | None = None


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or admin_instance is None:
            return False

        async with admin_instance.session_maker() as session:
            result = await session.execute(
                select(AdminUser).where(
                    AdminUser.username == username, AdminUser.is_active.is_(True)
                )
            )
            admin_user = result.scalar_one_or_none()
            if admin_user is None or not verify_password(password, admin_user.password_hash):
                return False

            admin_user_id = admin_user.id
            admin_user.last_login_at = utcnow()
            await session.commit()

        request.session.update({"admin_user_id": admin_user_id})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        admin_user_id = request.session.get("admin_user_id")
        if not admin_user_id or admin_instance is None:
            return False

        async with admin_instance.session_maker() as session:
            result = await session.execute(
                select(AdminUser).where(
                    AdminUser.id == admin_user_id, AdminUser.is_active.is_(True)
                )
            )
            return result.scalar_one_or_none() is not None


class PharmacyAdmin(ModelView, model=Pharmacy):
    name = "Pharmacy"
    name_plural = "Pharmacies"
    icon = "fa-solid fa-store"
    column_list = [
        Pharmacy.name,
        Pharmacy.latitude,
        Pharmacy.longitude,
        Pharmacy.rating,
    ]


class MedicationCatalogAdmin(ModelView, model=MedicationCatalog):
    name = "Medication"
    name_plural = "Medication Catalog"
    icon = "fa-solid fa-pills"
    column_list = [
        MedicationCatalog.name,
        MedicationCatalog.dosage,
        MedicationCatalog.unit,
        MedicationCatalog.form,
        MedicationCatalog.type,
        MedicationCatalog.retired_at,
    ]
    column_searchable_list = [MedicationCatalog.name]


class PharmacyPriceAdmin(ModelView, model=PharmacyPrice):
    name = "Price"
    name_plural = "Pharmacy Prices"
    icon = "fa-solid fa-tag"
    column_list = [PharmacyPrice.pharmacy_id, PharmacyPrice.catalog_id, PharmacyPrice.unit_price]


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False  # PII
    # Explicit allowlist -- pin_hash is deliberately excluded. A hashed
    # 6-digit PIN is still low-entropy enough that displaying it anywhere
    # is a real leak, not a tidiness concern.
    column_list = [
        User.phone_number,
        User.full_name,
        User.email,
        User.address,
        User.membership_activated_at,
        User.created_at,
        User.pin_failed_attempts,
        User.pin_locked_until,
    ]
    column_details_list = [User.id, *column_list]


class PrescriptionAdmin(ModelView, model=Prescription):
    name = "Prescription"
    name_plural = "Prescriptions"
    icon = "fa-solid fa-file-prescription"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        Prescription.user_id,
        Prescription.status,
        Prescription.image_url,
        Prescription.submitted_at,
    ]


class MedicationLineAdmin(ModelView, model=Medication):
    name = "Prescribed Medication"
    name_plural = "Prescribed Medications"
    icon = "fa-solid fa-prescription-bottle"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        Medication.prescription_id,
        Medication.name,
        Medication.dosage,
        Medication.dosage_unit,
        Medication.quantity,
        Medication.frequency,
    ]


class AdminUserAdmin(ModelView, model=AdminUser):
    name = "Admin Account"
    name_plural = "Admin Accounts"
    icon = "fa-solid fa-user-shield"
    can_create = False
    can_edit = False
    can_delete = False
    # Managed via scripts/manage_admin_users.py -- this view is visibility
    # only. password_hash is deliberately excluded, same reasoning as
    # User.pin_hash.
    column_list = [
        AdminUser.username,
        AdminUser.role,
        AdminUser.is_active,
        AdminUser.created_at,
        AdminUser.last_login_at,
    ]
    column_details_list = [AdminUser.id, *column_list]


def setup_admin(app: Starlette, engine: AsyncEngine) -> Admin:
    """Returns the constructed Admin instance (and stashes it on
    `admin_instance`) so tests can repoint `admin.session_maker` at a test
    database -- sqladmin's routes hold their own DB session_maker rather
    than going through FastAPI's `Depends(get_db)` override mechanism.
    """
    global admin_instance

    admin = Admin(
        app,
        engine,
        title="Pharmly Admin",
        authentication_backend=AdminAuth(secret_key=settings.jwt_secret),
    )
    for view in (
        PharmacyAdmin,
        MedicationCatalogAdmin,
        PharmacyPriceAdmin,
        UserAdmin,
        PrescriptionAdmin,
        MedicationLineAdmin,
        AdminUserAdmin,
    ):
        admin.add_view(view)

    admin_instance = admin
    return admin
