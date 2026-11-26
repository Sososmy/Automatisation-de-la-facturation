"""Configuration centrale (lue depuis .env)."""
from decimal import Decimal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    tax_rate: Decimal = Decimal("0.18")
    confidence_threshold: float = 0.80
    price_anomaly_threshold: float = 0.30
    app_user: str = "admin"
    app_password: str = ""


settings = Settings()
