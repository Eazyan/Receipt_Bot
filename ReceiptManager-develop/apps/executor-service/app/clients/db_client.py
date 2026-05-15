"""
Модуль для работы с API БД.
Реализует клиента для работы с БД.
Клиент реализует функции обновления, изменения, получения и создания записей.
"""


import httpx
from typing import Any, List
from app.core.config import settings
from app.core.logger import get_logger
from app.schemas.receipt_item import ReceiptItemCreate, ReceiptItemUpdate, ReceiptItemOut, ReceiptItemBatchOut
from app.schemas.receipt import ReceiptUpdate, ReceiptOut
from app.api.schemas import AssignmentOut, ParticipantOut, UserOut, UserCreate
from fastapi.encoders import jsonable_encoder


logger = get_logger(__name__)

    
class DBClient:
    """Клиент для взаимодействия с API БД"""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url if base_url else settings.database_api_url

        self.session = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=10.0
        )

        logger.info(f"Initialized client for DB API with base_url: {self.base_url}")

    async def close(self):
        """
        Метод для закрытия соединения при остановке приложения
        """
        await self.session.aclose()
        logger.info(f"DB API client session with base_url: {self.base_url} was closed")

    async def _request(
            self,
            method: str,
            path: str,
            **kwargs
    ) -> dict[str, Any] | None:
        """
        Базовый метод для всех запросов
        Args:
            method: метод HTTP запроса
            path: путь запроса
            **kwargs: словарь оставшихся именованных аргументов
        Returns:
            словарь - ответ от API
        """
        try:
            response = await self.session.request(method=method, url=path, **kwargs)
            logger.info(f"Response to DB API, method: {method}, path: {path}, status: {response.status_code}")
            response.raise_for_status()

            if response.status_code == 204 or not response.text:
                return None

            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"DB API error: {e.response.status_code}: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"DB API connection error: {e}")
            raise

    """
    Методы для изменения информации о позициях
    """
    async def add_items(
            self,
            receipt_id: int,
            payload: List[ReceiptItemCreate]
    ) -> ReceiptItemBatchOut:
        """
        Метод для добавления позиций
        Args:
            receipt_id: id чека для добавления новых позиций
            payload: список с информацией о новых позициях
        Returns:
            Валидированный объект, с информацией о добавленных позициях
        """

        data = jsonable_encoder(
            [item.model_dump(exclude_none=True) for item in payload]
        )

        response_data = await self._request(
            "POST",
            f"/items/{receipt_id}",
            json=data,
        )

        items_count = len(response_data.get("items", []))
        logger.info(f"Added {items_count} items to receipt {receipt_id}")

        return ReceiptItemBatchOut.model_validate(response_data)


    async def update_item(
            self,
            item_id: int,
            payload: ReceiptItemUpdate
    ) -> ReceiptItemOut:
        """
        Метод для обновления позиции
        Args:
            item_id: id позиции
            payload: информация для обновления позиции
        Returns:
            Валидированный объект с информацией об обновленной позиции
        """
        data = jsonable_encoder(
            payload.model_dump(exclude_unset=True)
        )

        response_data = await self._request(
            "PATCH",
            f"/items/{item_id}",
            json=data
        )

        return ReceiptItemOut.model_validate(response_data)


    async def get_item(
            self,
            item_id: int
    ) -> ReceiptItemOut | None:
        """Метод для получения позиции
        Args:
            item_id: id позиции
        Returns:
            Валидированный объект с информацией об искомой позиции. None, если объект не найден
        """
        try:
            response_data =  await self._request(
                "GET",
                f"/items/{item_id}",
            )

            return ReceiptItemOut.model_validate(response_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"Item with id {item_id} not found in DB.")
                return None
            raise


    async def get_receipt_items(
            self,
            receipt_id: int
    ) -> ReceiptItemBatchOut | None:
        """Метод для получения позиции
        Args:
            receipt_id: id чека
        Returns:
            Валидированный объект с информацией о блюдах в чеке. None, если чек не найден
        """
        try:
            response_data = await self._request(
                "GET",
                f"/receipts/{receipt_id}/items",
            )

            # возвращаем пустую схему
            if not response_data:
                return ReceiptItemBatchOut(items=[])

            return ReceiptItemBatchOut.model_validate(response_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"Receipt with id {receipt_id} not found in DB.")
                return None
            raise

    async def delete_item(
            self,
            item_id: int
    ) -> None:
        """Метод для удаления позиции
        Args:
            item_id: id позиции
        Returns:
            None: ничего не возвращает при успехе, либо выбрасывает исключение
        """
        await self._request(
            "DELETE",
            f"/items/{item_id}"
        )


    """
    Методы для изменения информации о чеках
    """
    async def update_receipt(
            self,
            receipt_id: int,
            payload: ReceiptUpdate
    ) -> dict[str, Any]:
        """
        Метод для обновления чека
        Args:
            receipt_id: id чека
            payload: информация для обновления чека
        Returns:
            словарь, элементы которого: поля обновленного чека
        """
        data = payload.model_dump(exclude_unset=True)
        return await self._request(
            "PATCH",
            f"/receipts/{receipt_id}",
            json=data
        )

    async def get_receipt(
            self,
            receipt_id: int
    ) -> ReceiptOut | None:
        """
        Метод для получения информации о чеке
        Args:
            receipt_id: id чека
        Returns:
            Валидированный объект с информацией о чеке. None, если чек не найден
        """
        try:
            response_data = await self._request(
                "GET",
                f"/receipts/{receipt_id}",
            )

            return ReceiptOut.model_validate(response_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"Receipt with id {receipt_id} not found in DB.")
                return None
            raise


    """
    Методы для работы с назначениями блюд на пользователей
    """
    async def assign_user_to_item(
            self,
            item_id: int,
            user_id: int,
            paid: str = "not paid"
    ) -> AssignmentOut:
        """
        Метод для назначения пользователя на блюдо (позицию в чеке)
        Args:
            item_id: id позиции
            user_id: id пользователя
            paid: статус оплаты (not paid, on review, paid)
        Returns:
            Валидированный объект с информацией о назначении
        """
        try:
            response_data = await self._request(
                "POST",
                f"/items/{item_id}/assignments/{user_id}",
                params={"paid": paid}
            )
            
            logger.info(f"User {user_id} assigned to item {item_id} with paid status: {paid}")
            return AssignmentOut.model_validate(response_data)
        except httpx.HTTPStatusError as e:
            # Если назначение уже существует, это нормальный результат
            if e.response.status_code == 409:
                logger.info(f"Assignment already exists for user {user_id} on item {item_id}")
                # Получаем существующее назначение
                assignments = await self.get_item_assignments(item_id)
                for assignment in assignments:
                    if assignment.user_id == user_id:
                        return assignment
                # Если почему-то не нашли, re-raise
                raise
            raise


    async def unassign_user_from_item(
            self,
            item_id: int,
            user_id: int
    ) -> None:
        """
        Метод для удаления назначения пользователя на блюдо
        Args:
            item_id: id позиции
            user_id: id пользователя
        Returns:
            None: ничего не возвращает при успехе, либо выбрасывает исключение
        """
        await self._request(
            "DELETE",
            f"/items/{item_id}/assignments/{user_id}"
        )
        
        logger.info(f"User {user_id} unassigned from item {item_id}")


    async def update_assignment_payment_status(
            self,
            item_id: int,
            user_id: int,
            paid: str
    ) -> AssignmentOut:
        """
        Метод для изменения статуса оплаты назначения
        Args:
            item_id: id позиции
            user_id: id пользователя
            paid: новый статус оплаты (not paid, on review, paid)
        Returns:
            Валидированный объект с обновленной информацией о назначении
        """
        response_data = await self._request(
            "PATCH",
            f"/items/{item_id}/assignments/{user_id}/paid",
            params={"paid": paid}
        )
        
        logger.info(f"Payment status for user {user_id} on item {item_id} updated to: {paid}")
        return AssignmentOut.model_validate(response_data)


    async def get_item_assignments(
            self,
            item_id: int
    ) -> List[AssignmentOut]:
        """
        Метод для получения списка всех назначений на блюдо
        Args:
            item_id: id позиции
        Returns:
            Список валидированных объектов с информацией о назначениях
        """
        try:
            response_data = await self._request(
                "GET",
                f"/items/{item_id}/assignments"
            )
            
            if not response_data:
                logger.info(f"No assignments found for item {item_id}")
                return []
            
            logger.info(f"Retrieved {len(response_data)} assignments for item {item_id}")
            return [AssignmentOut.model_validate(assignment) for assignment in response_data]
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"Item with id {item_id} not found in DB.")
                return []
            raise


    """
    Методы для работы с участниками комнаты
    """
    """
    Методы для работы с пользователями
    """
    async def create_user(
            self,
            payload: UserCreate
    ) -> UserOut:
        """
        Метод для создания пользователя
        Args:
            payload: информация для создания пользователя
        Returns:
            Валидированный объект с информацией о созданном пользователе
        """
        data = jsonable_encoder(
            payload.model_dump(exclude_none=True)
        )
        
        response_data = await self._request(
            "POST",
            "/users/",
            json=data
        )
        
        logger.info(f"User {payload.username} created successfully")
        return UserOut.model_validate(response_data)


    async def get_user(
            self,
            user_id: int
    ) -> UserOut | None:
        """
        Метод для получения информации о пользователе
        Args:
            user_id: id пользователя
        Returns:
            Валидированный объект с информацией о пользователе. None, если пользователь не найден
        """
        try:
            response_data = await self._request(
                "GET",
                f"/users/{user_id}"
            )
            
            logger.info(f"Retrieved user {user_id}")
            return UserOut.model_validate(response_data)
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"User with id {user_id} not found in DB.")
                return None
            raise


    async def update_user(
            self,
            user_id: int,
            username: str | None = None,
            user_public_name: str | None = None
    ) -> UserOut:
        """
        Метод для обновления информации о пользователе
        Args:
            user_id: id пользователя
            username: новое имя пользователя (опционально)
            user_public_name: новое публичное имя пользователя (опционально)
        Returns:
            Валидированный объект с обновленной информацией о пользователе
        """
        data = {}
        if username is not None:
            data["username"] = username
        if user_public_name is not None:
            data["user_public_name"] = user_public_name
        
        response_data = await self._request(
            "PATCH",
            f"/users/{user_id}",
            json=data
        )
        
        logger.info(f"User {user_id} updated successfully")
        return UserOut.model_validate(response_data)


    """  
    Методы для работы с участниками комнаты
    """
    async def get_room_participants(
            self,
            room_id: int
    ) -> List[ParticipantOut]:
        """
        Метод для получения списка участников комнаты
        Args:
            room_id: id комнаты
        Returns:
            Список валидированных объектов с информацией об участниках
        """
        try:
            response_data = await self._request(
                "GET",
                f"/rooms/{room_id}/participants"
            )
            
            # если комната существует но участников нет, вернем пустой список
            if not response_data:
                logger.info(f"No participants found in room {room_id}")
                return []
            
            logger.info(f"Retrieved {len(response_data)} participants from room {room_id}")
            return [ParticipantOut.model_validate(participant) for participant in response_data]
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"Room with id {room_id} not found in DB.")
                return []
            raise