import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.payment import PaymentTransaction
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


async def _auth_session(client: AsyncClient, fake_sms: FakeSmsSender, phone: str = PHONE) -> dict:
    session = await signup(client, fake_sms, phone)
    session["headers"] = {"Authorization": f"Bearer {session['access_token']}"}
    return session


async def _add_payment_transaction(
    db_session: AsyncSession,
    user_id: str,
    reference: str,
    amount: float,
    status: str = "success",
) -> None:
    db_session.add(
        PaymentTransaction(reference=reference, user_id=user_id, amount=amount, status=status)
    )
    await db_session.commit()


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


async def _add_product(
    db_session: AsyncSession, pharmacy_id: str, catalog_id: str, unit_price: float
) -> None:
    db_session.add(
        PharmacyProduct(pharmacy_id=pharmacy_id, catalog_id=catalog_id, unit_price=unit_price)
    )
    await db_session.commit()


async def _seed_orderable_prescription(
    client: AsyncClient,
    db_session: AsyncSession,
    headers: dict,
    pharmacy_id: str = "ph_1",
    unit_price: float = 2.0,
) -> dict:
    prescription = await _submit_prescription(client, headers, [MED_A])
    catalog = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, pharmacy_id, "Test Pharmacy")
    await _add_product(db_session, pharmacy_id, catalog.id, unit_price)
    return prescription


async def test_place_order_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/orders",
        json={"prescription_id": "x", "pharmacy_id": "ph_1", "payment_type": "cashOnDelivery"},
    )
    assert resp.status_code == 401


async def test_place_order_happy_path(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, headers)

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    order_id = resp.json()["order_id"]
    assert order_id

    detail = await client.get(f"/v1/orders/{order_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == order_id
    assert body["pharmacy_name"] == "Test Pharmacy"
    assert body["items_label"] == "Amoxicillin · 1 item"
    assert body["progress"] == "preparing"
    assert body["total"] == 21 * 2.0


async def test_place_order_computes_total_server_side_not_from_client(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, headers, unit_price=3.5)

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
            "total": 0.01,  # not part of the schema -- must be ignored, not just rejected
        },
        headers=headers,
    )
    assert resp.status_code == 201
    order_id = resp.json()["order_id"]

    detail = await client.get(f"/v1/orders/{order_id}", headers=headers)
    assert detail.json()["total"] == 21 * 3.5


async def test_place_order_is_idempotent_on_same_prescription(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, headers)

    payload = {
        "prescription_id": prescription["id"],
        "pharmacy_id": "ph_1",
        "payment_type": "cashOnDelivery",
    }
    first = await client.post("/v1/orders", json=payload, headers=headers)
    second = await client.post("/v1/orders", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["order_id"] == second.json()["order_id"]

    count = (
        await db_session.execute(
            select(Order).where(Order.prescription_id == prescription["id"])
        )
    ).scalars().all()
    assert len(count) == 1


async def test_place_order_idempotent_even_against_different_pharmacy(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, headers, "ph_1", 2.0)

    catalog = (
        await db_session.execute(select(MedicationCatalog))
    ).scalars().one()
    await _add_pharmacy(db_session, "ph_2", "Other Pharmacy")
    await _add_product(db_session, "ph_2", catalog.id, 9.0)

    first = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers,
    )
    second = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_2",
            "payment_type": "cashOnDelivery",
        },
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["order_id"] == second.json()["order_id"]

    detail = await client.get(f"/v1/orders/{first.json()['order_id']}", headers=headers)
    assert detail.json()["pharmacy_name"] == "Test Pharmacy"  # ph_1, the original order


async def test_place_order_404_on_someone_elses_prescription(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers_a = await _auth_headers(client, fake_sms, "+233241111111")
    prescription = await _seed_orderable_prescription(client, db_session, headers_a)

    headers_b = await _auth_headers(client, fake_sms, "+233242222222")
    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers_b,
    )
    assert resp.status_code == 404


async def test_place_order_404_if_pharmacy_does_not_exist(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])
    await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "does-not-exist",
            "payment_type": "cashOnDelivery",
        },
        headers=headers,
    )
    assert resp.status_code == 404


async def test_place_order_422_if_pharmacy_does_not_stock_medication(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers = await _auth_headers(client, fake_sms)
    prescription = await _submit_prescription(client, headers, [MED_A])
    await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, "ph_1", "Empty Pharmacy")
    # No PharmacyProduct row -- pharmacy exists but doesn't stock it.

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_get_orders_returns_only_own_newest_first(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers_a = await _auth_headers(client, fake_sms, "+233241111111")
    catalog = await _add_catalog_entry(db_session, "Amoxicillin", "500", "mg")
    await _add_pharmacy(db_session, "ph_1", "Test Pharmacy")
    await _add_product(db_session, "ph_1", catalog.id, 2.0)

    prescription_1 = await _submit_prescription(client, headers_a, [MED_A])
    order_1 = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription_1["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers_a,
    )
    prescription_2 = await _submit_prescription(client, headers_a, [MED_A])
    order_2 = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription_2["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers_a,
    )

    headers_b = await _auth_headers(client, fake_sms, "+233242222222")
    prescription_3 = await _submit_prescription(client, headers_b, [MED_A])
    await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription_3["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers_b,
    )

    resp = await client.get("/v1/orders", headers=headers_a)
    assert resp.status_code == 200
    ids = [o["id"] for o in resp.json()]
    assert ids == [order_2.json()["order_id"], order_1.json()["order_id"]]


async def test_get_order_404_on_someone_elses_order(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    headers_a = await _auth_headers(client, fake_sms, "+233241111111")
    prescription = await _seed_orderable_prescription(client, db_session, headers_a)
    order = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "cashOnDelivery",
        },
        headers=headers_a,
    )

    headers_b = await _auth_headers(client, fake_sms, "+233242222222")
    resp = await client.get(f"/v1/orders/{order.json()['order_id']}", headers=headers_b)
    assert resp.status_code == 404


async def test_place_order_422_if_payment_reference_missing_for_card_payment(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    session = await _auth_session(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, session["headers"])

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "card",
        },
        headers=session["headers"],
    )
    assert resp.status_code == 422


async def test_place_order_422_if_payment_not_successful(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    session = await _auth_session(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, session["headers"])
    await _add_payment_transaction(
        db_session, session["user"]["id"], "PSK-pending", amount=100.0, status="pending"
    )

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "card",
            "payment_reference": "PSK-pending",
        },
        headers=session["headers"],
    )
    assert resp.status_code == 422


async def test_place_order_422_if_payment_amount_insufficient(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    session = await _auth_session(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, session["headers"])
    # Order total will be 21 * 2.0 = 42.0 -- pay far too little.
    await _add_payment_transaction(
        db_session, session["user"]["id"], "PSK-short", amount=1.0, status="success"
    )

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "card",
            "payment_reference": "PSK-short",
        },
        headers=session["headers"],
    )
    assert resp.status_code == 422


async def test_place_order_succeeds_and_links_payment_transaction_for_successful_card_payment(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    session = await _auth_session(client, fake_sms)
    prescription = await _seed_orderable_prescription(client, db_session, session["headers"])
    await _add_payment_transaction(
        db_session, session["user"]["id"], "PSK-good", amount=100.0, status="success"
    )

    resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription["id"],
            "pharmacy_id": "ph_1",
            "payment_type": "card",
            "payment_reference": "PSK-good",
        },
        headers=session["headers"],
    )
    assert resp.status_code == 201
    order_id = resp.json()["order_id"]

    transaction = (
        await db_session.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == "PSK-good")
        )
    ).scalar_one()
    assert transaction.order_id == order_id
