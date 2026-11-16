from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.models import entities  # noqa: F401
from app.api.routes import router
from app.services.bootstrap import ensure_bootstrap_admin

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title=settings.app_name, version="0.2.0",
    description="AI real-estate lead intelligence for Portugal",
    docs_url="/api/v1/docs" if settings.environment.lower() not in {"prod", "production"} else None,
    openapi_url="/api/v1/openapi.json" if settings.environment.lower() not in {"prod", "production"} else None,
)
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.frontend_origin.rstrip("/")],
    allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
def startup():
    if settings.environment.lower() in {"prod", "production"}:
        if len(settings.secret_key) < 32 or settings.secret_key.startswith("CHANGE_ME"):
            raise RuntimeError("SECRET_KEY must be a unique random value of at least 32 characters in production")
    ensure_bootstrap_admin()

@app.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}
