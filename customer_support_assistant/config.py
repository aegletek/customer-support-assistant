from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
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

    app_name: str = "Customer Support Assistant"
    database_url: str = ""
    live_llm_enabled: bool = False

    provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    def require_database(self) -> None:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is required. Copy .env.example to .env and configure it locally."
            )

    def missing_live_llm_settings(self) -> list[str]:
        required = {
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "OPENROUTER_MODEL": self.openrouter_model,
            "LANGFUSE_PUBLIC_KEY": self.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": self.langfuse_secret_key,
            "LANGFUSE_HOST": self.langfuse_host,
        }
        return [name for name, value in required.items() if not value]

    def require_live_llm(self) -> None:
        if not self.live_llm_enabled:
            return
        if self.provider.lower() != "openrouter":
            raise RuntimeError("Live Customer Support currently requires PROVIDER=openrouter.")
        missing = self.missing_live_llm_settings()
        if missing:
            raise RuntimeError(
                "Missing live LLM configuration: "
                + ", ".join(missing)
                + ". Configure the values in the use-case .env file."
            )
