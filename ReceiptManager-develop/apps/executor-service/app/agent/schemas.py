from pydantic import BaseModel, Field
from typing import List
from typing_extensions import TypedDict, Annotated
from dataclasses import dataclass, field
from app.clients.db_client import DBClient
from app.schemas.receipt_item import ReceiptItemCreate, ReceiptItemUpdate, ReceiptItemBatchOut
from decimal import Decimal
import operator


# Receipt schemas
class ReceiptItemCreateSchema(BaseModel):
    """
    Сущность для создания позиции в чеке
    """
    name: str = Field(description="название позиции")
    price: float  = Field(description="стоимость позиции")
    quantity: float  = Field(default=1.0,
                             description="количетсво позиции в чеке, либо ее вес, если стоимость зависит от веса")

    def to_db_model(self) -> ReceiptItemCreate:
        return ReceiptItemCreate(
            name=self.name,
            price=Decimal(str(self.price)),
            quantity=Decimal(str(self.quantity))
        )

class ReceiptItemUpdateSchema(BaseModel):
    """
    Сущность для обновления данных позиции в чеке
    """
    name: str | None = Field(description="название позиции")
    price: float | None = Field(description="стоимость позиции")
    quantity: float | None = Field(default=1.0,
                            description="количетсво позиции в чеке, либо ее вес, если стоимость зависит от веса")

    def to_db_update(self) -> ReceiptItemUpdate:
        update_data = self.model_dump(exclude_unset=True)

        if "price" in update_data and update_data["price"] is not None:
            update_data["price"] = Decimal(str(update_data["price"]))
        if "quantity" in update_data and update_data["quantity"] is not None:
            update_data["quantity"] = Decimal(str(update_data["quantity"]))

        return ReceiptItemUpdate(**update_data)


class ReceiptUpdateSchema(BaseModel):
    """
    Сущность для обновления информации о чеке
    """
    paid_at: str | None = Field(
        default=None,
        description="Дата оплаты чека в формате YYYY-MM-DD или YYYY-MM-DD HH:MM:SS"
    )
    place_name: str | None = Field(
        default=None,
        description="Название заведения, где был совершен заказ"
    )

    def to_db_update(self):
        from app.schemas.receipt import ReceiptUpdate
        from datetime import datetime
        
        update_data = self.model_dump(exclude_unset=True, exclude_none=True)
        
        # Преобразуем строку даты в datetime
        if "paid_at" in update_data and update_data["paid_at"]:
            try:
                # Пытаемся парсить в разные форматы
                try:
                    update_data["paid_at"] = datetime.fromisoformat(update_data["paid_at"])
                except ValueError:
                    # Если не сработал ISO format, пробуем другой
                    update_data["paid_at"] = datetime.strptime(update_data["paid_at"], "%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                raise ValueError(f"Неверный формат даты: {update_data['paid_at']}. Используй YYYY-MM-DD или YYYY-MM-DD HH:MM:SS")
        
        return ReceiptUpdate(**update_data)


class ReceiptItemBatchCreateSchema(BaseModel):
    """
    Сущность с информацией о позициях для добавления в чек позициях
    """
    items: List[ReceiptItemCreateSchema] = Field(description="список позиций для добавления в чек")
    error: str | None = Field(description="Поле с текстом об ошибке, в случае если не получилось распарсить данные")


class ReceiptItemOutSchema(BaseModel):
    """
    Сущность - позиция в чеке
    """
    id: int = Field(description="Номер позиции в чеке")
    name: str = Field(description="название позиции")
    price: float  = Field(description="стоимость позиции")
    quantity: float  = Field(default=1.0,
                             description="количество позиции в чеке, либо ее вес, если стоимость зависит от веса")


class ReceiptItemBatchOutSchema(BaseModel):
    """
    Сущность с информацией о добавленных в чек позициях
    """
    items: List[ReceiptItemOutSchema] = Field(description="список добавленных позиций")



# Agent Context Schema



class AgentState(TypedDict):
    """
    Контекст, который прокидывается в tools агента.
    """
    messages: Annotated[list, operator.add]

    user_id: int

    receipt_id: int | None

    action_required: bool
    error: str | None



class AgentRoomState(TypedDict):
    """
    Контекст, который прокидывается в tools агента.
    """
    messages: Annotated[list, operator.add]

    user_id: int

    receipt_id: int | None

    assignment_updated: bool
    error: str | None



class AgentReceiptState(TypedDict):
    messages: Annotated[list, operator.add]

    user_id: int

    receipt_id: int | None

    receipt_updated: bool
    error: str | None



# Agent Response Schema



class ResponseFormatSchema(BaseModel):
    """
    Результат работы по запросу пользователя.
    """
    task: str = Field(description="Задача которую просил выполнить пользователь")
    made: bool = Field(default=True,
                       description="Достаточно ли текущей информации для выполнении задачи")
    error_message: str | None = Field(description="Сообщение о том, какую информацию необходимо предоставить, если текущей недостаточно")
    result: str = Field(description="Была ли задача успешно выполнена, если нет, то почему")
