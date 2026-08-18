from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.path = path
        self.details = details or {}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    trace_id = request.headers.get("X-Request-Id", "")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "path": exc.path,
                "details": exc.details,
                "traceId": trace_id,
            }
        },
    )
