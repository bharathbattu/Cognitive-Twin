import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
logger = logging.getLogger(__name__)
_STARTUP_CONFIGURATION_LOGGED = False


class Settings(BaseSettings):
    app_name: str = "Cognitive Twin"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    frontend_origin: str = "http://localhost:5173"

    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias="OPENROUTER_BASE_URL",
    )
    default_model: str = Field(..., validation_alias="DEFAULT_MODEL")

    memory_json_path: str = Field(default=str(PROJECT_ROOT / "data" / "json"))
    memory_faiss_path: str = Field(default=str(PROJECT_ROOT / "data" / "faiss"))
    embedding_dimension: int = 64

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("openrouter_api_key", "default_model", mode="before")
    @classmethod
    def validate_required_string(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "")
        env_name = "OPENROUTER_API_KEY" if field_name == "openrouter_api_key" else "DEFAULT_MODEL"
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing {env_name}. Set it in backend/.env")
        return value.strip()

    @field_validator("openrouter_base_url", mode="before")
    @classmethod
    def normalize_base_url(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "https://openrouter.ai/api/v1"
        return value.strip()

    @property
    def resolved_memory_json_path(self) -> Path:
        path = Path(self.memory_json_path)
        return (BACKEND_DIR / path).resolve() if not path.is_absolute() else path

    @property
    def resolved_memory_faiss_path(self) -> Path:
        path = Path(self.memory_faiss_path)
        return (BACKEND_DIR / path).resolve() if not path.is_absolute() else path


@lru_cache
def _load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise RuntimeError(_format_settings_error(exc)) from exc


def get_settings() -> Settings:
    global _STARTUP_CONFIGURATION_LOGGED

    settings = _load_settings()
    if not _STARTUP_CONFIGURATION_LOGGED and logging.getLogger().handlers:
        logger.info("OpenRouter configured")
        logger.info("Default model: %s", settings.default_model)
        _STARTUP_CONFIGURATION_LOGGED = True
    return settings


def _format_settings_error(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field_name = str(location[0]) if location else ""
        if field_name in {"openrouter_api_key", "OPENROUTER_API_KEY"}:
            message = "Missing OPENROUTER_API_KEY. Set it in backend/.env"
        elif field_name in {"default_model", "DEFAULT_MODEL"}:
            message = "Missing DEFAULT_MODEL. Set it in backend/.env"
        else:
            raw_message = str(error.get("msg", "Invalid application configuration."))
            message = raw_message.removeprefix("Value error, ").strip()
        if message not in messages:
            messages.append(message)
    return "\n".join(messages) or "Invalid application configuration."
