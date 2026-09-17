import logging

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from app.api.v1 import auth, me, orders, prescriptions
from app.core.config import settings
from app.core.exceptions import install_exception_handlers

# Minimal baseline so INFO-level app logs (e.g. the console SMS sender)
# aren't silently dropped -- root logger otherwise defaults to WARNING.
# Revisit for real structured logging (PRD §7) before production.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Pharmly API")

install_exception_handlers(app)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(prescriptions.router)
app.include_router(orders.router)

app.mount(
    "/uploads", StaticFiles(directory=settings.local_storage_dir, check_dir=False), name="uploads"
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
