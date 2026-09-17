import secrets

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.models.pharmacy import MedicationCatalog, Pharmacy, PharmacyPrice
from app.models.prescription import Medication, Prescription
from app.models.user import User


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = form.get("password")
        if isinstance(password, str) and secrets.compare_digest(password, settings.admin_password):
            request.session.update({"admin_authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        return bool(request.session.get("admin_authenticated"))


class PharmacyAdmin(ModelView, model=Pharmacy):
    name = "Pharmacy"
    name_plural = "Pharmacies"
    icon = "fa-solid fa-store"
    column_list = [
        Pharmacy.id,
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
        MedicationCatalog.id,
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
        User.id,
        User.phone_number,
        User.full_name,
        User.email,
        User.address,
        User.membership_activated_at,
        User.created_at,
        User.pin_failed_attempts,
        User.pin_locked_until,
    ]
    column_details_list = column_list


class PrescriptionAdmin(ModelView, model=Prescription):
    name = "Prescription"
    name_plural = "Prescriptions"
    icon = "fa-solid fa-file-prescription"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        Prescription.id,
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
        Medication.id,
        Medication.prescription_id,
        Medication.name,
        Medication.dosage,
        Medication.dosage_unit,
        Medication.quantity,
        Medication.frequency,
    ]


admin_instance: Admin | None = None


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
    ):
        admin.add_view(view)

    admin_instance = admin
    return admin
