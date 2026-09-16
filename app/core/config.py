from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "dev"

    database_url: str = "postgresql+asyncpg://pharmly:pharmly@localhost:5432/pharmly"

    jwt_secret: str = "change-me-in-env-please-use-a-random-32-byte-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    verification_token_expire_minutes: int = 10

    otp_length: int = 6
    otp_expire_minutes: int = 5
    otp_request_cooldown_seconds: int = 60
    otp_request_max_per_hour: int = 5

    pin_max_failed_attempts: int = 5
    pin_lockout_minutes: int = 15

    sms_provider: str = "console"  # "console" | "arkesel"
    arkesel_api_key: str | None = None
    arkesel_sender_id: str = "Pharmly"
    # None => infer from `environment` (sandbox everywhere except "prod").
    # Set explicitly to override that inference regardless of environment.
    arkesel_sandbox: bool | None = None

    storage_provider: str = "local"  # "local" for now; e.g. "s3" later
    local_storage_dir: str = "uploads"
    public_base_url: str = "http://localhost:8000"


settings = Settings()
