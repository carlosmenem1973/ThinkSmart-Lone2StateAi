from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.models import entities  # noqa: F401
from app.api.routes import router

# Schema changes are deployed through Alembic before the application rollout.
app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="ThinkSmart AI real-estate intelligence API",
    docs_url="/api/v1/docs" if settings.environment.lower() not in {"prod", "production"} else None,
    openapi_url="/api/v1/openapi.json" if settings.environment.lower() not in {"prod", "production"} else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin.rstrip("/")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
def startup():
    if not settings.cognito_user_pool_id or not settings.cognito_app_client_id:
        raise RuntimeError("COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID must be configured")

@app.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}
