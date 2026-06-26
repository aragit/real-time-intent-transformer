from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict


class Settings(BaseSettings):
    app_name: str = "real-time-intent-transformer"
    debug: bool = Field(default=False)
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_clicks: str = "ecommerce.clicks.raw"
    kafka_consumer_group: str = "intent-transformer"
    database_url: str = "sqlite:///./intent_transformer.db"
    opa_url: str = "http://localhost:8181/v1/data/ecommerce/allow"
    session_timeout_minutes: int = 30
    sliding_window_minutes: int = 5
    model_path: str = "./models/intent_classifier.joblib"

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
