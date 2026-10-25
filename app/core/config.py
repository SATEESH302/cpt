"""Validated application and database environment configuration."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="Diagnostic Platform API", min_length=1)
    app_version: str = Field(default="1.0.0", min_length=1)
    service_name: str = Field(default="diagnostic-platform-api", min_length=1)
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    db_host: str = Field(default="127.0.0.1", min_length=1)
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = Field(default="diagnostic_platform", min_length=1)
    db_user: str | None = Field(default=None, min_length=1)
    db_password: SecretStr | None = None
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_pool_timeout: int = Field(default=10, ge=1, le=120)
    db_pool_recycle: int = Field(default=1800, ge=1)
    db_connect_timeout: int = Field(default=5, ge=1, le=60)
    db_use_null_pool: bool = False
    db_verify_on_startup: bool = False
    auth_session_seconds: int = Field(default=3600, ge=60, le=86400)
    auth_rate_window_seconds: int = Field(default=900, ge=60, le=3600)
    auth_login_attempts: int = Field(default=10, ge=1, le=100)
    auth_ip_attempts: int = Field(default=50, ge=1, le=1000)

    @property
    def auth_secure_cookies(self) -> bool:
        return self.app_env in {"staging", "production"}

    @property
    def auth_cookie_name(self) -> str:
        return "__Host-dtp_session" if self.auth_secure_cookies else "dtp_session"

    @property
    def auth_csrf_cookie_name(self) -> str:
        return "__Host-dtp_csrf" if self.auth_secure_cookies else "dtp_csrf"

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", value):
            raise ValueError("API prefix must contain nonempty /path segments")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("Invalid origin port") from exc
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
                or any(char.isspace() for char in value)
                or (port is not None and port < 1)
                or value != f"{parsed.scheme}://{parsed.netloc}"
            ):
                raise ValueError(
                    "Origins must be explicit HTTP(S) scheme://host[:port]"
                )
        return list(dict.fromkeys(values))


@lru_cache
def get_settings() -> Settings:
    return Settings()
