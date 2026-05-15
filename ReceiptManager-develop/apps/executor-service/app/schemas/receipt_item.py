from decimal import Decimal
from typing import List
from pydantic import BaseModel, ConfigDict


class ReceiptItemCreate(BaseModel):
    name: str
    price: Decimal
    quantity: Decimal = Decimal("1.000")


class ReceiptItemUpdate(BaseModel):
    name: str | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None


class ReceiptItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    name: str
    price: Decimal
    quantity: Decimal

class ReceiptItemBatchOut(BaseModel):
    items: List[ReceiptItemOut]