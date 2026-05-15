from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus
from pydantic import computed_field
from functools import lru_cache
from typing import Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
while not (BASE_DIR / ".env").exists() and BASE_DIR.parent != BASE_DIR:
    BASE_DIR = BASE_DIR.parent
ENV_FILE = BASE_DIR / ".env"
print(f"Loading .env from: {ENV_FILE}")

class Settings(BaseSettings):
    """
    Конфигурация приложения.
    """

    # APPLICATION
    app_name: str = "LLM Agent API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"  # development | staging | production

    # API
    api_prefix: str = "/api"
    api_v1_prefix: str = "/api/v1"

    # CORS
    cors_origins: list[str] = ["http://localhost:5432", "http://localhost:8000"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # LLM (OpenRouter)
    openrouter_api_key: str | None = None

    openrouter_model: str | None = "qwen/qwen3.5-35b-a3b"

    openrouter_base_url: str | None = "https://openrouter.ai/api/v1"

    openrouter_temperature: float = 0.0
    openrouter_max_tokens: int = 4096
    openrouter_timeout: int = 30  # секунды

    # DATABASE API
    database_api_url: str | None = None

    # DATABASE RECEIPT CHECKPOINTER
    langgraph_receipt_db_name: str = "postgres"
    langgraph_receipt_db_user: str = "postgres"
    langgraph_receipt_db_password: str = ""
    langgraph_receipt_db_host: str = "localhost"
    langgraph_receipt_db_port_internal: int = 5432
    langgraph_receipt_db_port_external: int = 5431

    # DATABASE ROOM CHECKPOINTER
    langgraph_room_db_name: str = "postgres"
    langgraph_room_db_user: str = "postgres"
    langgraph_room_db_password: str = ""
    langgraph_room_db_host: str = "localhost"
    langgraph_room_db_port_internal: int = 5434
    langgraph_room_db_port_external: int = 5434

    @computed_field
    @property
    def langgraph_receipt_db_url(self) -> str:
        # экранирование пароля
        pwd = quote_plus(self.langgraph_receipt_db_password) if self.langgraph_receipt_db_password else ""

        return (
            f"postgresql://"
            f"{self.langgraph_receipt_db_user}:{pwd}"
            f"@{self.langgraph_receipt_db_host}:{self.langgraph_receipt_db_port_internal}"
            f"/{self.langgraph_receipt_db_name}"
        )

    @computed_field
    @property
    def langgraph_room_db_url(self) -> str:
        # экранирование пароля
        pwd = quote_plus(self.langgraph_room_db_password) if self.langgraph_room_db_password else ""

        return (
            f"postgresql://"
            f"{self.langgraph_room_db_user}:{pwd}"
            f"@{self.langgraph_room_db_host}:{self.langgraph_room_db_port_internal}"
            f"/{self.langgraph_room_db_name}"
        )


    # LOGGING
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    log_format: str = "text"  # json | text

    # TOOLS
    db_query_max_rows: int = 100
    db_query_timeout: int = 30

    # ASR SERVICE
    asr_service_host: str = "asr-service"
    asr_service_port: int = 5030
    asr_timeout_seconds: int = 10
    asr_temperature: int = 0
    
    @computed_field
    @property
    def asr_service_url(self) -> str:
        return f"http://{self.asr_service_host}:{self.asr_service_port}"

    # External API tools
    external_api_enabled: bool = True
    external_api_url: str | None = None
    external_api_key: str | None = None

    # Настройки Pydantic
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,  # Читать из .env файла
        env_file_encoding="utf-8",
        case_sensitive=False,  # DATABASE_URL == database_url
        extra="ignore",  # Игнорировать неизвестные переменные
    )
    
    def __init__(self, **data):
        super().__init__(**data)
        print("\n=== CONFIG LOADED VALUES ===")
        print(f"Receipt DB Host: {self.langgraph_receipt_db_host}")
        print(f"Receipt DB Port Internal: {self.langgraph_receipt_db_port_internal}")
        print(f"Receipt DB Name: {self.langgraph_receipt_db_name}")
        print(f"Receipt DB URL: {self.langgraph_receipt_db_url}")
        print(f"\nRoom DB Host: {self.langgraph_room_db_host}")
        print(f"Room DB Port Internal: {self.langgraph_room_db_port_internal}")
        print(f"Room DB Name: {self.langgraph_room_db_name}")
        print(f"Room DB URL: {self.langgraph_room_db_url}")
        print("=== END CONFIG ===\n")


# Singleton pattern для settings
@lru_cache
def get_settings() -> Settings:
    """
    Создаёт и кеширует единственный экземпляр настроек.
    Использует lru_cache, чтобы не парсить .env каждый раз.
    """
    return Settings()


# Удобный экспорт для импорта
settings = get_settings()