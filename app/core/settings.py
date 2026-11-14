from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/jobs.db"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    # Google's free tier for gemini-3.5-flash-lite: 15 requests a minute, 500 a day.
    gemini_rpm: int = 15
    gemini_daily_cap: int = 500
    http_min_interval_s: float = 2.5
    tz: str = "Asia/Kolkata"
    backup_push_target: str | None = None
    dashboard_password_hash: str | None = None
    dashboard_url: str | None = None  # e.g. http://pi:8000; adds a link to Telegram alerts


def get_settings() -> Settings:
    return Settings()
