from typing import Optional

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
    use_redis_store: bool = Field(default=False)
    redis_url: str = "redis://localhost:6379/0"
    use_pg_ledger: bool = Field(default=False)
    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/intent_transformer"
    postgres_read_replica_dsn: Optional[str] = None
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    llm_provider: str = "ollama"
    llm_model: str = "llama3"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    system_2_confidence_threshold: float = 0.70

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
