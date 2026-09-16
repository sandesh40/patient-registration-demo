import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine, text

from app.api.demo import router as demo_router
from app.api.dependencies import DatabaseSession
from app.api.patients import router as patients_router
from app.api.vapi import router as vapi_router
from app.config import Settings, get_settings
from app.db import build_engine
from app.errors import register_error_handlers
from app.schemas import Envelope

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    database_engine = engine or build_engine(settings.database_url.get_secret_value())
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Migrations run explicitly; never mutate the schema during a cold start.
        yield
        database_engine.dispose()

    application = FastAPI(
        title="Patient Registration API",
        description="Demo only: use fictional patient data. Dates use MM/DD/YYYY.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.engine = database_engine
    register_error_handlers(application)
    application.include_router(patients_router)
    application.include_router(vapi_router)
    application.include_router(demo_router)
    # Vercel moves public/ to its CDN and omits it from the Python function bundle.
    # Mount files only for local development; production static requests use the CDN.
    if (PUBLIC_DIR / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")

    @application.get("/", include_in_schema=False)
    def demo_page():
        if (PUBLIC_DIR / "index.html").is_file():
            return FileResponse(PUBLIC_DIR / "index.html")
        return RedirectResponse("/index.html")

    @application.get("/health", response_model=Envelope[dict[str, str]], tags=["health"])
    def health():
        """Liveness: the application is running."""
        return {"data": {"status": "ok"}, "error": None}

    @application.get("/ready", response_model=Envelope[dict[str, str]], tags=["health"])
    def ready(session: DatabaseSession):
        """Readiness: database connectivity and all registration tables are available."""
        session.execute(text("SELECT patient_id FROM patients LIMIT 0"))
        session.execute(text("SELECT call_id FROM voice_sessions LIMIT 0"))
        session.execute(text("SELECT call_id FROM voice_tool_receipts LIMIT 0"))
        return {"data": {"status": "ready"}, "error": None}

    return application


app = create_app()
