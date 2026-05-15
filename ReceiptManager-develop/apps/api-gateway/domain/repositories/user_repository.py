from abc import ABC, abstractmethod
from typing import Optional
from domain.entities.user import User

class UserRepository(ABC):

    @abstractmethod
    def save(self, user: User) -> None:
        """Сохранение пользователя"""
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[User]:
        """Поиск пользователя по id"""
        pass