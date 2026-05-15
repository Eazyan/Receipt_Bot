from enum import Enum
from functools import lru_cache
from langchain_openrouter import ChatOpenRouter
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class LLMProvider(str, Enum):
    """Поддерживаемые LLM провайдеры"""
    OPENROUTER = "openrouter"
    LMSTUDIO = "lmstudio"


class LLMFactory:
    """Фабрика для создания LLM на основе конфигурации"""

    @staticmethod
    def create_openrouter_llm() -> ChatOpenRouter:
        """Создаёт OpenRouter LLM"""
        logger.info(
            f"Initializing OpenRouter LLM: model={settings.openrouter_model}, "
        )

        return ChatOpenRouter(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            app_title=None,
            # timeout = settings.openrouter_timeout,
            streaming=False # пока False, надо разобраться с соединением
        )

    @classmethod
    def create(cls, provider: LLMProvider | None = None) -> BaseChatModel:
        """
        Создаёт LLM на основе провайдера.

        Args:
            provider: Провайдер LLM. Если None, используется из настроек.

        Returns:
            Инстанс LLM
        """
        provider = provider or LLMProvider.OPENROUTER

        match provider:
            case LLMProvider.OPENROUTER:
                return cls.create_openrouter_llm()
            case _:
                raise ValueError(f"Unsupported LLM provider: {provider}")


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """
    Возвращает singleton инстанс LLM.
    Кешируется для переиспользования.

    Returns:
        Настроенный LLM
    """
    return LLMFactory.create(LLMProvider.OPENROUTER)

