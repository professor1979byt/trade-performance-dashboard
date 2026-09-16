from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = False
    database_url: str = "postgresql+psycopg://trade:trade@localhost:5432/trade_performance"
    initial_backfill_days: int = 90
    pionex_api_key: str = ""
    pionex_api_secret: str = ""
    pionex_proxy_url: str = ""
    pionex_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
