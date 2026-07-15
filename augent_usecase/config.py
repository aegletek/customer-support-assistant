from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


class UseCaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Augent Use Case"
