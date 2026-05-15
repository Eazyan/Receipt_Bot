from abc import ABC, abstractmethod


class IdGenerator(ABC):
    """Интерфейс для генерации ID"""

    @abstractmethod
    def generate(self) -> str:
        """Сгенерировать уникальный ID"""
        pass