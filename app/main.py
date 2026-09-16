from fastapi import FastAPI

from app.api.v1 import auth, me
from app.core.exceptions import install_exception_handlers

app = FastAPI(title="Pharmly API")

install_exception_handlers(app)

app.include_router(auth.router)
app.include_router(me.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
