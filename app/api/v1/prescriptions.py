from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models.prescription import Prescription
from app.models.user import User
from app.schemas.prescription import MedicationIn, PrescriptionOut
from app.services.prescription_service import create_prescription, list_prescriptions

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])

_medications_adapter = TypeAdapter(list[MedicationIn])


@router.post("/submit", response_model=PrescriptionOut, status_code=status.HTTP_201_CREATED)
async def submit_prescription(
    medications: str = Form(...),
    image: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Prescription:
    try:
        parsed_medications = _medications_adapter.validate_json(medications)
    except ValidationError as err:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid medications payload."
        ) from err

    if not parsed_medications:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "At least one medication is required."
        )

    image_bytes = await image.read() if image is not None else None
    image_filename = image.filename if image is not None else None

    return await create_prescription(
        db, current_user.id, parsed_medications, image_bytes, image_filename
    )


@router.get("", response_model=list[PrescriptionOut])
async def get_prescriptions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    return await list_prescriptions(db, current_user.id)
