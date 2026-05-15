from pydantic import BaseModel, Field
from decimal import Decimal
from typing import List

class ParsedItemDTO(BaseModel):
    """Сырая позиция из чека, найденная OCR"""
    name: str
    quantity: Decimal
    price: Decimal = Decimal("0.00")


class ParsedReceiptDTO(BaseModel):
    """Формат ответа - сырой чек, найденный OCR"""
    paid_at: str = ""
    error: str | None = None
    items: List[ParsedItemDTO] = Field(default_factory=list)
    tip: Decimal = Decimal("0.00")
    service: Decimal = Decimal("0.00")
