import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.v1.router import api_router
from app.application.identity_security import add_audit_log, client_ip
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.db.session import SessionLocal


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]

    @application.middleware("http")
    async def audit_mutations(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = (request.headers.get("X-Request-Id") or str(uuid.uuid4()))[:80]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.url.path != f"{settings.api_v1_prefix}/auth/login"
            and getattr(request.state, "current_user_id", None) is not None
        ):
            try:
                with SessionLocal.begin() as audit_db:
                    segments = request.url.path.strip("/").split("/")
                    resource_type = segments[2] if len(segments) > 2 else None
                    resource_id = segments[3] if len(segments) > 3 else None
                    add_audit_log(
                        audit_db,
                        action=f"HTTP_{request.method}",
                        outcome="SUCCESS" if response.status_code < 400 else "FAILURE",
                        request_id=request_id,
                        ip_address=client_ip(request),
                        actor_user_id=request.state.current_user_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        details={"path": request.url.path, "statusCode": response.status_code},
                    )
            except Exception:  # pragma: no cover - audit failure must not break business requests
                pass
        return response

    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
