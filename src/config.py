"""Configuration centrale (lue depuis .env)."""
from decimal import Decimal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-5-5"
    anthropic_api_key: str = ""
    database_url: str = "sqlite:///./data/app.db"
    tax_rate: Decimal = Decimal("0.18")
    currency: str = "XOF"
    confidence_threshold: float = 0.80
    price_anomaly_threshold: float = 0.30


settings = Settings()
