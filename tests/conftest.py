from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services import otp_service


class FakeSmsSender:
    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def send_otp(self, phone_number: str, code: str) -> None:
        self.sent[phone_number] = code


@pytest.fixture
def fake_sms(monkeypatch: pytest.MonkeyPatch) -> FakeSmsSender:
    sender = FakeSmsSender()
    monkeypatch.setattr(otp_service, "get_sms_sender", lambda: sender)
    return sender


@pytest.fixture(autouse=True)
def _no_otp_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    # Most tests re-request an OTP for the same phone number within a single
    # test; only the dedicated rate-limit test cares about the real cooldown.
    monkeypatch.setattr(settings, "otp_request_cooldown_seconds", 0)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_maker() as session:
        yield session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
