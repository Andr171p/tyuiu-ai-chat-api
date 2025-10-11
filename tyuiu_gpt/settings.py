from typing import Final, Literal

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


class EmbeddingsSettings(BaseSettings):
    base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(env_prefix="EMBEDDINGS_")


class ElasticsearchSettings(BaseSettings):
    host: str = "localhost"
    port: int = 9200
    user: str = "esuser"
    password: str = "espassword"

    model_config = SettingsConfigDict(env_prefix="ELASTICSEARCH_")

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def auth(self) -> tuple[str, str]:
        return self.user, self.password


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/0"


class PostgresSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5432
    user: str = "pguser"
    password: str = "pgpassword"
    db: str = "postgres"
    driver: Literal["asyncpg"] = "asyncpg"

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql+{self.driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RabbitSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5672
    user: str = "rabbituser"
    password: str = "rabbitpassword"

    model_config = SettingsConfigDict(env_prefix="RABBIT_")

    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/"


class GigaChatSettings(BaseSettings):
    apikey: str = ""
    scope: str = ""
    model_name: str = "GigaChat:lite"

    model_config = SettingsConfigDict(env_prefix="GIGACHAT_")


class YandexGPTSettings(BaseSettings):
    folder_id: str = ""
    apikey: str = ""

    model_config = SettingsConfigDict(env_prefix="YANDEXGPT_")


class Settings(BaseSettings):
    embeddings: EmbeddingsSettings = EmbeddingsSettings()
    elasticsearch: ElasticsearchSettings = ElasticsearchSettings()
    redis: RedisSettings = RedisSettings()
    postgres: PostgresSettings = PostgresSettings()
    rabbit: RabbitSettings = RabbitSettings()
    gigachat: GigaChatSettings = GigaChatSettings()
    yandexgpt: YandexGPTSettings = YandexGPTSettings()


settings: Final[Settings] = Settings()
