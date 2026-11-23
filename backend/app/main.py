
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models import entities  # noqa: F401
from app.models import contact_ai  # noqa: F401
from app.models import analytics  # noqa: F401
from app.api.routes import router
from app.api.contact_ai import router as contact_ai_router
from app.api.analytics import router as analytics_router


app = FastAPI(
    title=settings.app_name,
    version="0.3.1",
    description="ThinkSmart AI real-estate intelligence API",
    docs_url=(
        "/api/v1/docs"
        if settings.environment.lower() not in {"prod", "production"}
        else None
    ),
    openapi_url=(
        "/api/v1/openapi.json"
        if settings.environment.lower() not in {"prod", "production"}
        else None
    ),
)

# Frontend origins allowed to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.webportal.thinksmart.pt",
        "https://webportal.thinksmart.pt",
    ],
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
    ],
)

app.include_router(router, prefix="/api/v1")
app.include_router(contact_ai_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


@app.on_event("startup")
def startup():
    if not settings.cognito_user_pool_id:
        raise RuntimeError(
            "COGNITO_USER_POOL_ID must be configured"
        )

    if not settings.cognito_app_client_id:
        raise RuntimeError(
            "COGNITO_APP_CLIENT_ID must be configured"
        )


@app.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}
