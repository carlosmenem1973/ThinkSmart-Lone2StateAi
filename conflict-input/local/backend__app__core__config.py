from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ThinkSmart AI"
    environment: str = "development"
    secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    cookie_secure: bool | None = None
    database_url: str = "postgresql+psycopg://estateai:estateai@db:5432/estateai"
    redis_url: str = "redis://redis:6379/0"

    # AWS: keep all service clients in the selected account/region.
    aws_region: str = "eu-west-1"
    bedrock_model_id: str = "eu.amazon.nova-lite-v1:0"
    agentcore_web_search_id: str = "web-search.v1"
    agentcore_web_search_max_results: int = 10

    # Existing Cognito configuration ÔÇö unchanged.
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
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
