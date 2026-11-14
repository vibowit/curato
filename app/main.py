import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import AppException, app_exception_handler
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


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
    yield
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
