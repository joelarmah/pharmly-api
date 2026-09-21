import base64
import binascii

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApiError
from app.models.pharmacy import DosageUnit, MedicationCatalog, MedicationType
from app.schemas.catalog import (
    CatalogMetadataResponse,
    CatalogSearchResponse,
    MedicationCatalogEntryOut,
)

_CURSOR_SEP = "\x00"

_LOAD_OPTIONS = (
    selectinload(MedicationCatalog.type),
    selectinload(MedicationCatalog.form),
    selectinload(MedicationCatalog.unit),
)


def _encode_cursor(name: str, entry_id: str) -> str:
    raw = f"{name}{_CURSOR_SEP}{entry_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        name, entry_id = raw.split(_CURSOR_SEP, 1)
    except (ValueError, binascii.Error) as err:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid cursor.") from err
    return name, entry_id


def _entry_out(entry: MedicationCatalog) -> MedicationCatalogEntryOut:
    return MedicationCatalogEntryOut(
        id=entry.id,
        name=entry.name,
        dosage=entry.dosage,
        unit=entry.unit.name,
        form=entry.form.name,
        type=entry.type.name,
    )


async def search_catalog(
    db: AsyncSession,
    search: str | None,
    limit: int,
    cursor: str | None,
) -> CatalogSearchResponse:
    stmt = (
        select(MedicationCatalog)
        .options(*_LOAD_OPTIONS)
        .where(MedicationCatalog.retired_at.is_(None))
        .order_by(MedicationCatalog.name, MedicationCatalog.id)
        .limit(limit + 1)  # one extra row to know whether there's a next page
    )
    if search:
        stmt = stmt.where(MedicationCatalog.name.ilike(f"%{search}%"))
    if cursor:
        cursor_name, cursor_id = _decode_cursor(cursor)
        # Explicit OR rather than a tuple_() comparison -- portable across
        # both Postgres (prod) and SQLite (tests) without relying on row-
        # value comparison support.
        stmt = stmt.where(
            or_(
                MedicationCatalog.name > cursor_name,
                (MedicationCatalog.name == cursor_name) & (MedicationCatalog.id > cursor_id),
            )
        )

    rows = (await db.execute(stmt)).scalars().all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].name, rows[-1].id)

    return CatalogSearchResponse(entries=[_entry_out(r) for r in rows], next_cursor=next_cursor)


async def get_metadata(db: AsyncSession) -> CatalogMetadataResponse:
    types = (
        (await db.execute(select(MedicationType.name).order_by(MedicationType.name)))
        .scalars()
        .all()
    )
    units = (
        (await db.execute(select(DosageUnit.name).order_by(DosageUnit.name))).scalars().all()
    )
    return CatalogMetadataResponse(types=list(types), dosage_units=list(units))
