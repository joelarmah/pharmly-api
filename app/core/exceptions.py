from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """Raise this (or HTTPException) for any error response.

    Always serializes as {"message": "..."} to match the mobile client's
    error mapper, regardless of whether `detail` is a plain string or a
    {"message": ...} dict.
    """

    def __init__(self, status_code: int, message: str, headers: dict | None = None):
        super().__init__(status_code=status_code, detail={"message": message}, headers=headers)


def _message_from_detail(detail: object) -> str:
    if isinstance(detail, dict) and "message" in detail:
        return str(detail["message"])
    if isinstance(detail, str):
        return detail
    return "Something went wrong."


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": _message_from_detail(exc.detail)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"message": "Invalid request."},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Something went wrong. Please try again."},
        )
