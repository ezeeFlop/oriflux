"""Runtime settings for all three entrypoints (env-driven, ORIFLUX_ prefix).

The single hardcoded API key pair is walking-skeleton scope only; real
scoped API keys stored in PostgreSQL arrive with issue #3.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORIFLUX_")

    redis_url: str = "redis://localhost:6379/0"

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "oriflux"
    clickhouse_password: str = "oriflux-dev"
    clickhouse_database: str = "oriflux"

    # Walking-skeleton auth: one ingest key and one read key, mapped to one org/project.
    ingest_api_key: str = "dev-ingest-key"
    read_api_key: str = "dev-read-key"
    org_id: str = "org-dev"
    project_id: str = "proj-dev"

    batch_size: int = 500
    batch_block_ms: int = 1000


def get_settings() -> Settings:
    return Settings()
