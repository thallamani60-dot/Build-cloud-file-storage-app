import logging
import re
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from starlette.middleware import Middleware
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.file_routes import router as file_router
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.database.session import engine


configure_logging()
logger = logging.getLogger("cloud_file_storage.access")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Private, authenticated file storage backed by Amazon S3.",
    middleware=[Middleware(SlowAPIMiddleware)],
)
app.state.limiter = limiter
register_exception_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_id) else str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(file_router, prefix="/api/v1/files", tags=["Files"])


@app.get("/app", include_in_schema=False)
def landing_page():
    return FileResponse(
        Path(__file__).parent / "static" / "index.html",
        media_type="text/html",
    )


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": "cloud-file-storage"}


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "available"}
