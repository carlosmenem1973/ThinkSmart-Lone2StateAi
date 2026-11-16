from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "ThinkSmart-Lone2StateAi"
    environment: str = "development"
    secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    cookie_secure: bool | None = None
    database_url: str = "postgresql+psycopg://estateai:estateai@db:5432/estateai"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-6-astra"
    openai_web_search_enabled: bool = True
    frontend_origin: str = "http://localhost:5173"
    microsoft_tenant_id: str = "common"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "https://estateai.example.pt/api/v1/integrations/microsoft/callback"
    google_maps_api_key: str = ""
    lead_score_threshold: int = 60
    default_country: str = "Portugal"
    timezone: str = "Europe/Lisbon"

settings = Settings()
