import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_response(status: int, code: str, message: str, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        content={
            "data": None,
            "error": {"code": code, "message": message, "details": details or []},
        },
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        invalid_json = any(error["type"] == "json_invalid" for error in exc.errors())
        # Do not echo submitted patient values, request bodies, or exception context.
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]),
                "message": error["msg"],
                "code": error["type"],
            }
            for error in exc.errors()
        ]
        return error_response(
            400 if invalid_json else 422,
            "invalid_json" if invalid_json else "validation_error",
            "Request body is not valid JSON"
            if invalid_json
            else "Please correct the indicated fields",
            details,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail), headers=exc.headers)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("database_error method=%s exception=%s", request.method, type(exc).__name__)
        return error_response(
            500, "database_error", "Unable to access patient records. Please retry."
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("unexpected_error method=%s exception=%s", request.method, type(exc).__name__)
        return error_response(500, "internal_error", "An unexpected error occurred. Please retry.")
