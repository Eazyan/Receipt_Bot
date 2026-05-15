from abc import ABC, abstractmethod
from typing import Optional, List
from domain.entities.room import Room


class RoomRepository(ABC):

    @abstractmethod
    def save(self, room: Room) -> None:
        """Сохранение комнаты"""
        pass

    @abstractmethod
    def get_by_id(self, room_id: str) -> Optional[Room]:
        """Поиск комнаты по id"""
        pass

    @abstractmethod
    def delete(self, room_id: str) -> None:
        """Удаление комнаты по id"""
        pass

    @abstractmethod
    def find_active_rooms(self, user_id: str) -> List[Room]:
        """Поиск активных комнат пользователя"""