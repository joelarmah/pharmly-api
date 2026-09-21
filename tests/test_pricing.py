import json

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pharmacy import MedicationCatalog, Pharmacy, PharmacyProduct
from tests.conftest import FakeSmsSender
from tests.helpers import PHONE, signup

MED_A = {
    "id": "client-uuid-a",
    "name": "Amoxicillin",
    "dosage": "500",
    "dosage_unit": "mg",
    "quantity": 21,
    "quantity_unit": "capsule",
    "type": "pills",
    "dose_amount": 1,
    "duration_days": 7,
    "reminder_enabled": True,
    "notification_days": ["Mon", "Wed", "Fri"],
    "frequency": "Twice Daily",
    "times": ["8:00 AM", "8:00 PM"],
    "start_from": "2026-09-16T08:00:00.000",
    "end_on": "2026-09-23T20:00:00.000",
}
MED_B = {**MED_A, "id": "client-uuid-b", "name": "Paracetamol", "dosage": "500", "quantity": 10}


async def _auth_headers(client: AsyncClient, fake_sms: FakeSmsSender, phone: str = PHONE) -> dict:
    session = await signup(client, fake_sms, phone)
    return {"Authorization": f"Bearer {session['access_token']}"}


async def _submit_prescription(client: AsyncClient, headers: dict, medications: list[dict]) -> dict:
    resp = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps(medications)},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _add_catalog_entry(
    db_session: AsyncSession, name: str, dosage: str, unit: str = "mg", type_: str = "pills"
) -> MedicationCatalog:
    entry = MedicationCatalog(name=name, dosage=dosage, unit=unit, form="tablet", type=type_)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


async def _add_pharmacy(
    db_session: AsyncSession,
    pharmacy_id: str,
    name: str,
    latitude: float = 5.6,
    longitude: float = -0.18,
    rating: float | None = 4.5,
) -> Pharmacy:
    pharmacy = Pharmacy(
        id=pharmacy_id, name=name, latitude=latitude, longitude=longitude, rating=rating
    )
    db_session.add(pharmacy)
    await db_session.commit()
    return pharmacy


async def _add_price(
    db_session: AsyncSession, pharmacy_id: str, catalog_id: str, unit_price: float
) -> None:
    db_session.add(
        PharmacyProduct(pharmacy_id=pharmacy_id, catalog_id=catalog_id, unit_price=unit_price)
    )
    await db_session.commit()


async def test_pricing_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/orders/pricing", json={"prescription_id": "PR123", "order_type": "singleLine"}
    )
    assert resp.status_code == 401


async def test_pricing_404_on_someone_elses_prescription(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers_a = await _auth_headers(client, fake_sms, "+233241111111")
    prescription = await _submit_prescription(client, headers_a, [MED_A])

    headers_b = await _auth_headers(client, fake_sms, "+233242222222")
    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "singleLine"},
        headers=headers_b,
    )
    assert resp.status_code == 404


async def test_single_line_happy_path_sorted_by_price(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])

    catalog = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, "ph_cheap", "Cheap Pharmacy")
    await _add_pharmacy(db_session, "ph_pricey", "Pricey Pharmacy")
    await _add_price(db_session, "ph_cheap", catalog.id, 2.0)
    await _add_price(db_session, "ph_pricey", catalog.id, 5.0)

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "singleLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    offers = resp.json()
    assert [o["pharmacy_id"] for o in offers] == ["ph_cheap", "ph_pricey"]
    assert offers[0]["total_price"] == 21 * 2.0
    assert offers[0]["is_fully_in_stock"] is True
    assert offers[0]["currency"] == "GHS"
    assert offers[0]["distance_km"] is None
    assert offers[0]["eta_minutes"] is None


async def test_single_line_partial_stock(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A, MED_B])

    catalog_a = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    catalog_b = await _add_catalog_entry(db_session, "Paracetamol", "500", "mg")
    await _add_pharmacy(db_session, "ph_full", "Full Stock Pharmacy")
    await _add_pharmacy(db_session, "ph_partial", "Partial Stock Pharmacy")
    await _add_price(db_session, "ph_full", catalog_a.id, 2.0)
    await _add_price(db_session, "ph_full", catalog_b.id, 1.0)
    await _add_price(db_session, "ph_partial", catalog_a.id, 2.0)

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "singleLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    offers = {o["pharmacy_id"]: o for o in resp.json()}
    assert offers["ph_full"]["is_fully_in_stock"] is True
    assert offers["ph_full"]["total_price"] == 21 * 2.0 + 10 * 1.0
    assert offers["ph_partial"]["is_fully_in_stock"] is False
    assert offers["ph_partial"]["total_price"] == 21 * 2.0


async def test_single_line_excludes_pharmacy_with_no_matching_items(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])

    catalog = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, "ph_has_it", "Has It Pharmacy")
    await _add_pharmacy(db_session, "ph_empty", "Empty Pharmacy")
    await _add_price(db_session, "ph_has_it", catalog.id, 2.0)

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "singleLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    offers = resp.json()
    assert [o["pharmacy_id"] for o in offers] == ["ph_has_it"]


async def test_single_line_no_catalog_match_returns_empty(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])
    # No catalog entry seeded at all.

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "singleLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_single_line_computes_distance_and_eta_when_coordinates_sent(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])

    catalog = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, "ph_1", "Pharmacy 1", latitude=5.6, longitude=-0.18)
    await _add_price(db_session, "ph_1", catalog.id, 2.0)

    resp = await client.post(
        "/v1/orders/pricing",
        json={
            "prescription_id": prescription["id"],
            "order_type": "singleLine",
            "latitude": 5.6,
            "longitude": -0.18,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    offer = resp.json()[0]
    assert offer["distance_km"] == 0.0
    assert isinstance(offer["eta_minutes"], int)
    assert offer["eta_minutes"] > 0


async def test_multi_line_different_pharmacies_win_different_medications(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A, MED_B])

    catalog_a = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    catalog_b = await _add_catalog_entry(db_session, "Paracetamol", "500", "mg")
    await _add_pharmacy(db_session, "ph_a_only", "Amox Only Pharmacy")
    await _add_pharmacy(db_session, "ph_b_only", "Paracetamol Only Pharmacy")
    await _add_price(db_session, "ph_a_only", catalog_a.id, 2.0)
    await _add_price(db_session, "ph_b_only", catalog_b.id, 1.0)

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "multiLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    lines = {line["name"]: line for line in resp.json()}

    assert [o["pharmacy_id"] for o in lines["Amoxicillin"]["offers"]] == ["ph_a_only"]
    assert lines["Amoxicillin"]["offers"][0]["subtotal"] == 21 * 2.0
    assert [o["pharmacy_id"] for o in lines["Paracetamol"]["offers"]] == ["ph_b_only"]
    assert lines["Paracetamol"]["offers"][0]["subtotal"] == 10 * 1.0


async def test_multi_line_medication_with_no_pharmacy_has_empty_offers(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])
    await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    # Catalog entry exists but no pharmacy carries it.

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "multiLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    lines = resp.json()
    assert len(lines) == 1
    assert lines[0]["offers"] == []


async def test_multi_line_offers_sorted_by_unit_price(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])

    catalog = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, "ph_expensive", "Expensive Pharmacy")
    await _add_pharmacy(db_session, "ph_cheap", "Cheap Pharmacy")
    await _add_price(db_session, "ph_expensive", catalog.id, 9.0)
    await _add_price(db_session, "ph_cheap", catalog.id, 1.0)

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": prescription["id"], "order_type": "multiLine"},
        headers=headers,
    )
    assert resp.status_code == 200
    offers = resp.json()[0]["offers"]
    assert [o["pharmacy_id"] for o in offers] == ["ph_cheap", "ph_expensive"]
