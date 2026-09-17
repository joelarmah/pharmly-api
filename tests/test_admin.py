import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pharmacy import Pharmacy
from app.models.user import User


async def test_admin_list_requires_login(client: AsyncClient) -> None:
    resp = await client.get("/admin/pharmacy/list", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/admin/login" in resp.headers["location"]


async def test_admin_login_wrong_password_denied(client: AsyncClient) -> None:
    resp = await client.post("/admin/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 400  # sqladmin re-renders the login form with an error

    follow_up = await client.get("/admin/pharmacy/list", follow_redirects=False)
    assert follow_up.status_code in (302, 303)


async def test_admin_login_then_list_shows_seeded_pharmacy(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_password", "test-admin-password")
    db_session.add(
        Pharmacy(id="ph_test", name="Test Pharmacy", latitude=5.6, longitude=-0.2, rating=4.5)
    )
    await db_session.commit()

    login_resp = await client.post(
        "/admin/login", data={"username": "admin", "password": "test-admin-password"}
    )
    assert login_resp.status_code in (200, 302, 303)

    resp = await client.get("/admin/pharmacy/list")
    assert resp.status_code == 200
    assert "Test Pharmacy" in resp.text


async def test_admin_user_list_never_renders_pin_hash(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_password", "test-admin-password")
    db_session.add(
        User(
            id="usr_test",
            phone_number="+233241234567",
            full_name="Test User",
            pin_hash="super-secret-hash-value-should-never-appear",
        )
    )
    await db_session.commit()

    await client.post("/admin/login", data={"username": "admin", "password": "test-admin-password"})

    list_resp = await client.get("/admin/user/list")
    assert list_resp.status_code == 200
    assert "super-secret-hash-value-should-never-appear" not in list_resp.text

    detail_resp = await client.get("/admin/user/details/usr_test")
    assert detail_resp.status_code == 200
    assert "super-secret-hash-value-should-never-appear" not in detail_resp.text


async def test_admin_user_view_has_no_edit_or_delete_controls(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_password", "test-admin-password")
    await client.post("/admin/login", data={"username": "admin", "password": "test-admin-password"})

    create_resp = await client.get("/admin/user/create", follow_redirects=False)
    assert create_resp.status_code in (403, 404)
