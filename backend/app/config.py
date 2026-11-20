from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    es_catalog_url: str = "http://localhost:9200"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change_me_please"
    cassandra_hosts: str = "localhost"
    es_logs_url: str = "http://localhost:9201"
    api_log_file: str = "./logs/api.log"


settings = Settings()
