from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pharmacy import DosageUnit, MedicationCatalog, MedicationForm, MedicationType
from tests.conftest import FakeSmsSender
from tests.helpers import PHONE, signup


async def _auth_headers(client: AsyncClient, fake_sms: FakeSmsSender, phone: str = PHONE) -> dict:
    session = await signup(client, fake_sms, phone)
    return {"Authorization": f"Bearer {session['access_token']}"}


async def _get_or_create(db_session: AsyncSession, model: type, name: str):
    existing = (
        await db_session.execute(select(model).where(model.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = model(name=name)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


async def _add_catalog_entry(
    db_session: AsyncSession,
    name: str,
    dosage: str = "500",
    unit: str = "mg",
    form: str = "tablet",
    type_: str = "pills",
    retired: bool = False,
) -> MedicationCatalog:
    unit_row = await _get_or_create(db_session, DosageUnit, unit)
    form_row = await _get_or_create(db_session, MedicationForm, form)
    type_row = await _get_or_create(db_session, MedicationType, type_)
    entry = MedicationCatalog(
        name=name,
        dosage=dosage,
        unit_id=unit_row.id,
        form_id=form_row.id,
        type_id=type_row.id,
        retired_at=datetime(2026, 1, 1) if retired else None,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


async def test_search_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/v1/medications/catalog")
    assert resp.status_code == 401


async def test_metadata_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/v1/medications/catalog/metadata")
    assert resp.status_code == 401


async def test_search_returns_matching_entries_case_insensitive(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    await _add_catalog_entry(db_session, "Amoxicillin")
    await _add_catalog_entry(db_session, "Paracetamol")

    resp = await client.get(
        "/v1/medications/catalog", params={"search": "amox"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [e["name"] for e in body["entries"]] == ["Amoxicillin"]
    assert body["entries"][0]["unit"] == "mg"
    assert body["entries"][0]["form"] == "tablet"
    assert body["entries"][0]["type"] == "pills"
    assert body["next_cursor"] is None


async def test_search_excludes_retired_entries(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    await _add_catalog_entry(db_session, "Amoxicillin", retired=True)

    resp = await client.get(
        "/v1/medications/catalog", params={"search": "amox"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


async def test_search_with_no_query_returns_first_page(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    await _add_catalog_entry(db_session, "Amoxicillin")
    await _add_catalog_entry(db_session, "Paracetamol")

    resp = await client.get("/v1/medications/catalog", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 2


async def test_search_pagination_cursor_returns_remaining_entries(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    names = ["Amoxicillin", "Ampicillin", "Azithromycin"]
    for name in names:
        await _add_catalog_entry(db_session, name)

    first = await client.get(
        "/v1/medications/catalog", params={"limit": 2}, headers=headers
    )
    assert first.status_code == 200
    first_body = first.json()
    assert [e["name"] for e in first_body["entries"]] == names[:2]
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/v1/medications/catalog",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
        headers=headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [e["name"] for e in second_body["entries"]] == names[2:]
    assert second_body["next_cursor"] is None


async def test_search_invalid_cursor_returns_422(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)
    resp = await client.get(
        "/v1/medications/catalog", params={"cursor": "not-valid-base64!!"}, headers=headers
    )
    assert resp.status_code == 422


async def test_metadata_returns_distinct_types_and_units(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    await _add_catalog_entry(db_session, "Amoxicillin", unit="mg", type_="pills")
    await _add_catalog_entry(db_session, "Cough Syrup", unit="mL", type_="liquid")

    resp = await client.get("/v1/medications/catalog/metadata", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["types"] == ["liquid", "pills"]
    assert body["dosage_units"] == ["mL", "mg"]
