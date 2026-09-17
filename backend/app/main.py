from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.routes.dashboard import router as dashboard_router
from backend.app.api.v1.routes.onboarding import router as onboarding_router
from backend.app.api.v1.routes.health import router as health_router
from backend.app.api.v1.routes.hypotheses import router as hypotheses_router
from backend.app.api.v1.routes.profile import router as profile_router
from backend.app.api.v1.routes.quick_add import router as quick_add_router
from backend.app.api.v1.routes.receipts import router as receipts_router
from backend.app.api.v1.routes.statements import router as statements_router
from backend.app.core.config import get_settings
from backend.app.db.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(settings.telegram_webapp_url),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(onboarding_router)
    app.include_router(quick_add_router)
    app.include_router(profile_router)
    app.include_router(receipts_router)
    app.include_router(statements_router)
    app.include_router(hypotheses_router)
    app.include_router(dashboard_router)
    return app


def _cors_origins(webapp_url: str) -> list[str]:
    origins = {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
    parsed = urlsplit(webapp_url)
    if parsed.scheme and parsed.netloc:
        origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(origins)


app = create_app()
