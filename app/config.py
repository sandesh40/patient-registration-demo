from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("sqlite+pysqlite:///./data/patients.db")
    api_auth_token: SecretStr = SecretStr("")
    vapi_webhook_secret: SecretStr = SecretStr("")
    vapi_assistant_id: str = ""
    vapi_public_key: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def production_settings(self) -> "Settings":
        if self.app_env == "production":
            if len(self.api_auth_token.get_secret_value()) < 32:
                raise ValueError("Production requires an API_AUTH_TOKEN of at least 32 characters")
            if not self.database_url.get_secret_value().startswith("postgresql"):
                raise ValueError("Production requires persistent PostgreSQL storage")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
