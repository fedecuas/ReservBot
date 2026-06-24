from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # WhatsApp — WA_* vars take precedence over legacy names
    whatsapp_token: str = Field(default="", validation_alias=AliasChoices("wa_access_token", "whatsapp_token"))
    phone_number_id: str = Field(default="", validation_alias=AliasChoices("wa_phone_number_id", "phone_number_id"))
    verify_token: str = Field(default="", validation_alias=AliasChoices("wa_verify_token", "verify_token"))
    app_secret: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Google Calendar
    google_credentials_json: str = "./credentials/service_account.json"
    google_calendar_id: str = "primary"

    # Redis (opcional — si está vacío usa SQLite)
    redis_url: str = ""

    # Database
    database_url: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Security
    cron_secret: str = ""
    platform_api_key: str = ""

    # Frontend URL for CORS (production)
    frontend_url: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
