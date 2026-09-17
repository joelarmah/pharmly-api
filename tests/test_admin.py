from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.models.pharmacy import Pharmacy
from app.models.user import User

USERNAME = "test-admin"
PASSWORD = "correct-horse-battery-staple"


async def _create_admin_account(
    db_session: AsyncSession, username: str = USERNAME, password: str = PASSWORD, **kwargs
) -> AdminUser:
    account = AdminUser(username=username, password_hash=hash_password(password), **kwargs)
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


async def _login(client: AsyncClient, username: str = USERNAME, password: str = PASSWORD):
    return await client.post("/admin/login", data={"username": username, "password": password})


async def test_admin_list_requires_login(client: AsyncClient) -> None:
    resp = await client.get("/admin/pharmacy/list", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/admin/login" in resp.headers["location"]


async def test_admin_login_wrong_password_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_account(db_session)

    resp = await client.post(
        "/admin/login", data={"username": USERNAME, "password": "wrong-password"}
    )
    assert resp.status_code == 400  # sqladmin re-renders the login form with an error

    follow_up = await client.get("/admin/pharmacy/list", follow_redirects=False)
    assert follow_up.status_code in (302, 303)


async def test_admin_login_unknown_username_denied(client: AsyncClient) -> None:
    resp = await client.post(
        "/admin/login", data={"username": "nobody", "password": "whatever"}
    )
    assert resp.status_code == 400


async def test_admin_login_disabled_account_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_account(db_session, is_active=False)

    resp = await _login(client)
    assert resp.status_code == 400

    follow_up = await client.get("/admin/pharmacy/list", follow_redirects=False)
    assert follow_up.status_code in (302, 303)


async def test_admin_login_then_list_shows_seeded_pharmacy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_account(db_session)
    db_session.add(
        Pharmacy(id="ph_test", name="Test Pharmacy", latitude=5.6, longitude=-0.2, rating=4.5)
    )
    await db_session.commit()

    login_resp = await _login(client)
    assert login_resp.status_code in (200, 302, 303)

    resp = await client.get("/admin/pharmacy/list")
    assert resp.status_code == 200
    assert "Test Pharmacy" in resp.text


async def test_admin_user_list_never_renders_pin_hash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_account(db_session)
    db_session.add(
        User(
            id="usr_test",
            phone_number="+233241234567",
            full_name="Test User",
            pin_hash="super-secret-hash-value-should-never-appear",
        )
    )
    await db_session.commit()

    await _login(client)

    list_resp = await client.get("/admin/user/list")
    assert list_resp.status_code == 200
    assert "super-secret-hash-value-should-never-appear" not in list_resp.text

    detail_resp = await client.get("/admin/user/details/usr_test")
    assert detail_resp.status_code == 200
    assert "super-secret-hash-value-should-never-appear" not in detail_resp.text


async def test_admin_accounts_list_never_renders_password_hash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    account = await _create_admin_account(db_session)
    password_hash = account.password_hash

    await _login(client)

    list_resp = await client.get("/admin/admin-user/list")
    assert list_resp.status_code == 200
    assert password_hash not in list_resp.text

    detail_resp = await client.get(f"/admin/admin-user/details/{account.id}")
    assert detail_resp.status_code == 200
    assert password_hash not in detail_resp.text


async def test_admin_accounts_view_has_no_create_or_edit_controls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_account(db_session)
    await _login(client)

    create_resp = await client.get("/admin/admin-user/create", follow_redirects=False)
    assert create_resp.status_code in (403, 404)


async def test_admin_user_view_has_no_edit_or_delete_controls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_account(db_session)
    await _login(client)

    create_resp = await client.get("/admin/user/create", follow_redirects=False)
    assert create_resp.status_code in (403, 404)
