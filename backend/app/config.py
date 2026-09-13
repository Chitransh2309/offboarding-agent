from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    token_encryption_key: str

    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_project_id: str | None = None

    github_app_id: str | None = None
    github_app_slug: str | None = None
    github_app_private_key: str | None = None
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None

    slack_client_id: str | None = None
    slack_client_secret: str | None = None

    notion_client_id: str | None = None
    notion_client_secret: str | None = None

    linear_client_id: str | None = None
    linear_client_secret: str | None = None

    github_webhook_secret: str | None = None
    linear_webhook_secret: str | None = None

    github_api_base_url: str = "https://api.github.com"
    slack_api_base_url: str = "https://slack.com/api"
    notion_api_base_url: str = "https://api.notion.com/v1"
    linear_api_base_url: str = "https://api.linear.app/graphql"

    arga_api_base_url: str = "https://api.argalabs.com"

    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    # Comma-separated extra origins allowed to call the API — e.g. a
    # deployed Vercel URL, in addition to the local dev frontend.
    extra_cors_origins: str = ""
    environment: str = "development"

    @property
    def cors_allowed_origins(self) -> list[str]:
        extras = [o.strip() for o in self.extra_cors_origins.split(",") if o.strip()]
        return [self.frontend_base_url, *extras]


@lru_cache
def get_settings() -> Settings:
    return Settings()
