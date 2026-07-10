"""Runtime settings for all three entrypoints (env-driven, ORIFLUX_ prefix)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORIFLUX_")

    redis_url: str = "redis://localhost:6379/0"

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "oriflux"
    clickhouse_password: str = "oriflux-dev"
    clickhouse_database: str = "oriflux"

    database_url: str = "postgresql+asyncpg://oriflux:oriflux-dev@localhost:5432/oriflux"

    # Dashboard auth (JWT + Google OAuth, ClipHaven pattern)
    jwt_secret: str = "dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    google_client_id: str = ""

    # Ingest protection (PRD §9): per-key and per-IP rate limits, events/minute
    api_key_cache_ttl_s: float = 30.0
    ingest_rate_limit_per_key: int = 600
    ingest_rate_limit_per_ip: int = 1200

    # Enrichment (issue #4): local GeoLite2 databases + weekly refresh
    geoip_dir: str = "./geoip"
    maxmind_license_key: str = ""
    ops_webhook_url: str = ""  # backup/refresh failure alerts (same as stack sidecars)

    # Alerting (issue #11)
    resend_api_key: str = ""  # empty → email channel disabled
    alert_email_from: str = "oriflux@sponge-theory.io"
    allow_private_webhooks: bool = False  # dev/test sinks only — NEVER in prod

    batch_size: int = 500
    batch_block_ms: int = 1000


def get_settings() -> Settings:
    return Settings()
