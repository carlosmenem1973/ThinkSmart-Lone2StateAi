
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "ThinkSmart AI"
    environment: str = "development"
    secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Bootstrap administrator
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    # Session and database
    cookie_secure: bool | None = None
    database_url: str = (
        "postgresql+psycopg://estateai:estateai@db:5432/estateai"
    )
    redis_url: str = "redis://redis:6379/0"

    # AWS
    aws_region: str = "eu-west-1"
    communications_sqs_queue_url: str = ""

    # Amazon Bedrock - Nova Lite
    bedrock_region: str = "eu-west-1"
    bedrock_model_id: str = "eu.amazon.nova-lite-v1:0"
    # Optional multimodal model used only for user-requested listing photo analysis.
    bedrock_vision_model_id: str = "eu.amazon.nova-2-lite-v1:0"

    # AgentCore Web Search
    bedrock_web_search_enabled: bool = True
    bedrock_web_search_id: str = "web-search.v1"
    agentcore_web_search_id: str = "web-search.v1"
    agentcore_web_search_max_results: int = 10

    # Amazon Cognito
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    frontend_origin: str = "http://localhost:5173"

    # Meta WhatsApp Cloud API webhook (secrets must come from AWS Secrets Manager)
    meta_whatsapp_verify_token: str = ""
    meta_whatsapp_app_secret: str = ""
    meta_whatsapp_phone_number_id: str = ""
    meta_whatsapp_access_token: str = ""
    meta_graph_api_version: str = "v26.0"

    # Outbound email via Amazon SES (no Microsoft 365 tenant admin consent required)
    email_from_address: str = "contacto@cbloft2.pt"
    ses_sender_verified: bool = False

    # Microsoft 365 integration
    microsoft_tenant_id: str = "common"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = (
        "https://estateai.example.pt/api/v1/integrations/microsoft/callback"
    )

    # External services
    google_maps_api_key: str = ""

    # Real estate business configuration
    lead_score_threshold: int = 60
    default_country: str = "Portugal"
    timezone: str = "Europe/Lisbon"


settings = Settings()
