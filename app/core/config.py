from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # WhatsApp
    whatsapp_token: str
    phone_number_id: str
    verify_token: str
    app_secret: str

    # Anthropic
    anthropic_api_key: str

    # Google Calendar
    google_credentials_json: str = "./credentials/service_account.json"
    google_calendar_id: str = "primary"

    # Redis (opcional — si está vacío usa SQLite)
    redis_url: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
