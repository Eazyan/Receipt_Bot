from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
while not (BASE_DIR / ".env").exists() and BASE_DIR.parent != BASE_DIR:
    BASE_DIR = BASE_DIR.parent
ENV_FILE = BASE_DIR / ".env"
print(f"Loading .env from: {ENV_FILE}")


class Settings(BaseSettings):
    """
    ASR Service Configuration
    """
    
    # APPLICATION
    app_name: str = "ASR Service"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"  # development | staging | production
    
    # API
    api_prefix: str = "/api"
    api_v1_prefix: str = "/api/v1"
    
    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://localhost:3000",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    
    # OPENROUTER ASR
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    asr_model: str = "mistralai/voxtral-mini-transcribe"
    asr_fallback_models: str = "qwen/qwen3-asr-flash-2026-02-10,openai/gpt-4o-mini-transcribe,openai/whisper-large-v3"
    asr_temperature: float = 0.0
    asr_timeout: int = 30  # seconds
    
    # LOGGING
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    log_format: str = "text"  # json | text
    
    # Settings configuration
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    def __init__(self, **data):
        super().__init__(**data)
        print("\n=== ASR SERVICE CONFIG LOADED ===")
        print(f"Model: {self.asr_model}")
        print(f"OpenRouter Base URL: {self.openrouter_base_url}")
        print(f"Debug: {self.debug}")
        print(f"Environment: {self.environment}")
        print("=" * 35)


@staticmethod
def get_settings() -> Settings:
    """
    Returns singleton instance of Settings
    """
    return Settings()
