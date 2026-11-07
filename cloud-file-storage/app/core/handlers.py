import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded

from app.core.exceptions import APIError

logger = logging.getLogger(__name__)


def _error_response(request: Request, status_code: int, code: str, message: str, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    response = JSONResponse(
        status_code=status_code,
        content={"error": error, "request_id": getattr(request.state, "request_id", None)},
    )
    if status_code == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return _error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Exclude submitted values from logs and responses (they may contain passwords).
        details = [
            {"location": list(item.get("loc", ())), "message": item.get("msg"), "type": item.get("type")}
            for item in exc.errors()
        ]
        return _error_response(request, 422, "validation_error", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = {
            401: "not_authenticated",
            403: "forbidden",
            404: "not_found",
        }.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed"
        return _error_response(request, exc.status_code, code, message)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        response = _error_response(request, 429, "rate_limit_exceeded", "Too many requests")
        response.headers["Retry-After"] = "60"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError):
        logger.exception("Database operation failed")
        return _error_response(request, 503, "database_unavailable", "Database operation failed")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled request error")
        return _error_response(request, 500, "internal_error", "An unexpected error occurred")
