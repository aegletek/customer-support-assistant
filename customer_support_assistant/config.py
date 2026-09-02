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

    provider: str = "azure"
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_temperature: float = 0.2
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = Field(default="https://cloud.langfuse.com")
    langfuse_project_url: str = ""

    def require_database(self) -> None:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is required. Copy .env.example to .env and configure it locally."
            )

    def missing_live_llm_settings(self) -> list[str]:
        required = {
            "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": self.azure_openai_api_key,
            "AZURE_OPENAI_DEPLOYMENT": self.azure_openai_deployment,
            "LANGFUSE_PUBLIC_KEY": self.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": self.langfuse_secret_key,
            "LANGFUSE_BASE_URL": self.langfuse_base_url,
            "LANGFUSE_PROJECT_URL": self.langfuse_project_url,
        }
        return [name for name, value in required.items() if not value]

    def require_live_llm(self) -> None:
        if not self.live_llm_enabled:
            return
        if self.provider.lower() != "azure":
            raise RuntimeError("Live Customer Support requires PROVIDER=azure.")
        missing = self.missing_live_llm_settings()
        if missing:
            raise RuntimeError(
                "Missing live LLM configuration: "
                + ", ".join(missing)
                + ". Configure the values in the use-case .env file."
            )
