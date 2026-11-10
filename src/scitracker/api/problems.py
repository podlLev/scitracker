import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from scitracker.api.middleware import REQUEST_ID_HEADER
from scitracker.domain.errors import (
    AuthenticationError,
    DomainError,
    DuplicateRecordError,
    InvalidStatusTransitionError,
    InvalidValueError,
    PermissionDeniedError,
    QuotaExceededError,
    RecordNotFoundError,
)

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"
TYPE_PREFIX = "urn:scitracker:problem:"


class FieldError(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    """Error body, RFC 9457 (application/problem+json)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "urn:scitracker:problem:validation-error",
                "title": "Request validation failed",
                "status": 422,
                "detail": "One or more request parameters are invalid.",
                "instance": "/api/v1/publications",
                "errors": [{"field": "query.limit", "message": "Input should be >= 1"}],
            }
        }
    )

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[FieldError] | None = None


class ApiProblem(Exception):  # noqa: N818 - reads better than ApiProblemError
    """A problem raised by the API layer itself (not by the domain)."""

    def __init__(self, status: int, slug: str, title: str, detail: str | None = None) -> None:
        super().__init__(detail or title)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail


_DOMAIN_PROBLEMS: tuple[tuple[type[DomainError], int, str, str], ...] = (
    (
        InvalidStatusTransitionError,
        409,
        "invalid-status-transition",
        "Status change is not allowed",
    ),
    (DuplicateRecordError, 409, "duplicate-record", "Record already exists"),
    (RecordNotFoundError, 404, "not-found", "Resource not found"),
    (AuthenticationError, 401, "authentication-failed", "Authentication required"),
    (PermissionDeniedError, 403, "forbidden", "Forbidden"),
    (QuotaExceededError, 409, "quota-exceeded", "Quota exceeded"),
    (InvalidValueError, 422, "invalid-value", "Invalid value"),
    (DomainError, 400, "domain-error", "Request violates a domain rule"),
)
_HTTP_SLUGS = {404: "not-found", 405: "method-not-allowed"}


def problem_response(  # noqa: PLR0913
    request: Request,
    status: int,
    slug: str,
    title: str,
    *,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        type=f"{TYPE_PREFIX}{slug}",
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        errors=errors,
    )
    return JSONResponse(
        body.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_JSON,
        headers=dict(headers) if headers else None,
    )


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def _api_problem(request: Request, exc: ApiProblem) -> JSONResponse:
        return problem_response(request, exc.status, exc.slug, exc.title, detail=exc.detail)

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        for error_class, status, slug, title in _DOMAIN_PROBLEMS:
            if isinstance(exc, error_class):
                headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
                return problem_response(
                    request, status, slug, title, detail=str(exc), headers=headers
                )
        raise exc  # pragma: no cover - DomainError itself is in the table

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Only the location and the message: the submitted value is never echoed back.
        errors = [
            FieldError(field=".".join(str(part) for part in e["loc"]), message=e["msg"])
            for e in exc.errors()
        ]
        return problem_response(
            request,
            422,
            "validation-error",
            "Request validation failed",
            detail="One or more request parameters are invalid.",
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        phrase = HTTPStatus(exc.status_code).phrase
        slug = _HTTP_SLUGS.get(exc.status_code, f"http-{exc.status_code}")
        detail = None if exc.detail == phrase else str(exc.detail)
        return problem_response(
            request, exc.status_code, slug, phrase, detail=detail, headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id: str | None = getattr(request.state, "request_id", None)
        logger.error(
            "unhandled error on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
            extra={"request_id": request_id},  # the context variable is already reset here
        )
        return problem_response(
            request,
            500,
            "internal-error",
            "Internal Server Error",
            detail="Unexpected error. Please try again later.",
            headers={REQUEST_ID_HEADER: request_id} if request_id else None,
        )
