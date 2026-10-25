from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.mark.parametrize("overrides", [
    {"app_env": "unknown"}, {"port": 0}, {"port": 65536},
    {"api_v1_prefix": "api/v1"}, {"api_v1_prefix": "/api/v1/"},
    {"api_v1_prefix": "/api//v1"}, {"api_v1_prefix": "/api?secret"},
    {"log_level": "TRACE"}, {"cors_origins": ["*"]},
    {"cors_origins": ["https://*.test"]},
    {"cors_origins": ["https://example.test/path"]},
    {"cors_origins": ["https://user:password@example.test"]},
    {"cors_origins": ["https://example.test?secret"]},
    {"cors_origins": ["https://example.test:99999"]},
    {"cors_origins": ["ftp://example.test"]},
])
def test_invalid_settings(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_dotenv_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'APP_VERSION=3.0.0\nPORT=8080\nDEBUG=false\n'
        'CORS_ORIGINS=["https://frontend.example.test"]\n', encoding="utf-8"
    )
    monkeypatch.setenv("PORT", "9090")
    settings = Settings(_env_file=env_file)
    assert settings.app_version == "3.0.0"
    assert settings.port == 9090
    assert settings.debug is False
    assert settings.cors_origins == ["https://frontend.example.test"]


def test_cached_settings() -> None:
    assert get_settings() is get_settings()
