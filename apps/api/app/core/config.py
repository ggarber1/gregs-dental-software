import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ───────────────────────────────────────────────────────────────────
    api_env: str = Field(default="development")
    api_port: int = Field(default=8000)
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(...)

    @property
    def async_database_url(self) -> str:
        """Always returns a postgresql+asyncpg:// URL regardless of how DATABASE_URL is stored."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── AWS ───────────────────────────────────────────────────────────────────
    aws_region: str = Field(default="us-east-1")
    aws_endpoint_url: str | None = Field(default=None)  # None in prod, localstack URL in dev

    s3_bucket_phi_documents: str = Field(default="dental-phi-documents-local")
    s3_bucket_era_files: str = Field(default="dental-era-files-local")
    s3_bucket_exports: str = Field(default="dental-exports-local")

    sqs_queue_reminders: str = Field(default="dental-reminders-queue")
    sqs_queue_eligibility: str = Field(default="dental-eligibility-queue")
    sqs_queue_era: str = Field(default="dental-era-queue")
    sqs_queue_audit_logs: str = Field(default="dental-audit-logs-queue")

    # ── Cognito ───────────────────────────────────────────────────────────────
    cognito_user_pool_id: str = Field(default="")
    cognito_client_id: str = Field(default="")
    cognito_region: str = Field(default="us-east-1")

    # ── Encryption ────────────────────────────────────────────────────────────
    # 32-byte base64-encoded key for AES-256 application-layer encryption (PHI)
    app_encryption_key: str = Field(default="")

    # ── App URL ───────────────────────────────────────────────────────────────
    # Public URL of the web frontend — used to build intake form links in SMS
    app_url: str = Field(default="http://localhost:3000")

    # ── Twilio ────────────────────────────────────────────────────────────────
    # Leave blank in development — SMS will be logged, not sent
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_from_number: str = Field(default="")

    # ── SES ───────────────────────────────────────────────────────────────────
    # Leave blank in development — email will be logged, not sent
    ses_from_address: str = Field(default="")
    ses_configuration_set: str = Field(default="")

    # ── Ambient Notes / Whisper ───────────────────────────────────────────────
    # Leave blank in development unless running the Whisper service locally
    whisper_endpoint_url: str = Field(default="")

    # ── Bedrock ───────────────────────────────────────────────────────────────
    bedrock_region: str = Field(default="us-east-1")
    bedrock_model_id: str = Field(default="anthropic.claude-haiku-4-5-20251001-v1:0")

    @property
    def is_development(self) -> bool:
        return self.api_env == "development"

    @property
    def is_production(self) -> bool:
        return self.api_env == "production"

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_api_cors_origins(cls, value: object) -> object:
        """
        Accept both JSON arrays and plain comma-delimited values in env vars.

        Examples:
          API_CORS_ORIGINS='["http://localhost:3000"]'
          API_CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:3000'
          API_CORS_ORIGINS='http://localhost:3000'
        """
        if value is None:
            return ["http://localhost:3000"]
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return value

        raw = value.strip()
        if raw == "":
            return ["http://localhost:3000"]

        if raw.startswith("["):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Fall back to comma split if env value is malformed JSON.
                pass

        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings populates fields from env
