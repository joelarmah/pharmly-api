from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApiError
from app.models.prescription import Medication, Prescription
from app.schemas.prescription import MedicationIn
from app.services.storage import StorageError, get_file_storage


async def create_prescription(
    db: AsyncSession,
    user_id: str,
    medications: list[MedicationIn],
    image_bytes: bytes | None,
    image_filename: str | None,
) -> Prescription:
    prescription = Prescription(user_id=user_id, status="submitted")
    db.add(prescription)
    await db.flush()  # assigns prescription.id

    for position, med in enumerate(medications):
        db.add(
            Medication(
                prescription_id=prescription.id,
                position=position,
                name=med.name,
                dosage=med.dosage,
                dosage_unit=med.dosage_unit,
                quantity=med.quantity,
                quantity_unit=med.quantity_unit,
                type=med.type,
                dose_amount=med.dose_amount,
                duration_days=med.duration_days,
                reminder_enabled=med.reminder_enabled,
                notification_days=med.notification_days,
                frequency=med.frequency,
                times=med.times,
                start_from=med.start_from,
                end_on=med.end_on,
            )
        )

    if image_bytes is not None:
        try:
            image_url = await get_file_storage().save_prescription_image(
                prescription.id, image_filename or "upload", image_bytes
            )
        except StorageError as err:
            raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
        prescription.image_url = image_url

    await db.commit()
    await db.refresh(prescription, attribute_names=["medications"])
    return prescription


async def list_prescriptions(db: AsyncSession, user_id: str) -> list[Prescription]:
    result = await db.execute(
        select(Prescription)
        .where(Prescription.user_id == user_id)
        .options(selectinload(Prescription.medications))
        .order_by(Prescription.submitted_at.desc())
    )
    return list(result.scalars().all())
