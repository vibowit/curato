import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import AppException, app_exception_handler
from app.core.logging import setup_logging
from app.core.scheduler import start_scheduler, stop_scheduler
from app.mcp.server import mcp_server

logger = logging.getLogger(__name__)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """Protects MCP SSE endpoints when MCP_API_KEY is configured."""

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization")
        query_token = request.query_params.get("api_key")

        valid = False
        if auth_header and auth_header == f"Bearer {self.api_key}":
            valid = True
        elif query_token and query_token == self.api_key:
            valid = True

        if not valid:
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Invalid or missing MCP API key."},
            )

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context managing startup and shutdown."""
    setup_logging()
    settings.ensure_data_dir()
    logger.info(
        "Application starting up: %s v%s (%s)",
        settings.PROJECT_NAME,
        settings.VERSION,
        settings.ENVIRONMENT,
    )
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Application shutting down...")


def create_app() -> FastAPI:
    """Factory function for creating and configuring the FastAPI app."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID / Correlation ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    # Exception handlers
    app.add_exception_handler(AppException, app_exception_handler)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled server error [req_id=%s]: %s", req_id, str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected internal server error occurred",
                "request_id": req_id,
                "details": None,
            },
        )

    # Include API routes
    app.include_router(api_router)

    # Mount MCP SSE subapp (supports local & remote SSE clients like ChatGPT)
    from mcp.server.transport_security import TransportSecuritySettings

    mcp_subapp = mcp_server.sse_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    if settings.MCP_API_KEY:
        mcp_subapp.add_middleware(
            MCPAuthMiddleware,
            api_key=settings.MCP_API_KEY.get_secret_value(),
        )
    app.mount("/mcp", mcp_subapp)

    # Serve static frontend files if directory exists
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    if os.path.exists(frontend_dir):

        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(os.path.join(frontend_dir, "index.html"))

        @app.get("/styles.css", include_in_schema=False)
        async def serve_css():
            return FileResponse(os.path.join(frontend_dir, "styles.css"), media_type="text/css")

        @app.get("/app.js", include_in_schema=False)
        async def serve_js():
            return FileResponse(
                os.path.join(frontend_dir, "app.js"), media_type="application/javascript"
            )

    return app


app = create_app()
