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


# Field-name -> human-readable format hint, for fields whose raw pydantic
# pattern-mismatch message (a regex) isn't something a client should have
# to interpret. Keyed by field name rather than by pattern since e.g. PIN
# and OTP `code` share the same "6 digits" pattern but need different copy.
_FIELD_FORMAT_HINTS: dict[str, str] = {
    "phone_number": "Phone number must be in international format, e.g. +233244245902.",
    "pin": "PIN must be exactly 6 digits.",
    "current_pin": "Current PIN must be exactly 6 digits.",
    "new_pin": "New PIN must be exactly 6 digits.",
    "code": "Code must be exactly 6 digits.",
}


def _describe_validation_error(error: dict) -> str:
    loc = error.get("loc", ())
    field = str(loc[-1]) if loc else None
    error_type = error.get("type", "")

    if error_type == "missing":
        return f"'{field}' is required." if field else "A required field is missing."

    if field in _FIELD_FORMAT_HINTS:
        return _FIELD_FORMAT_HINTS[field]

    if error_type == "literal_error":
        expected = error.get("ctx", {}).get("expected")
        if field and expected:
            return f"'{field}' must be one of: {expected}."

    return f"Invalid value for '{field}'." if field else "Invalid request."


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
        errors = exc.errors()
        message = _describe_validation_error(errors[0]) if errors else "Invalid request."
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"message": message},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Something went wrong. Please try again."},
        )
