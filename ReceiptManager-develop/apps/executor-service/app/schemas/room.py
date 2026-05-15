from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

class RoomUpdate(BaseModel):
    name: str | None = None
    receipt_id: int | None = None
    status: str | None = None
    payment_details: str | None = None
    receipt_comment: str | None = None
    is_active: bool | None = None


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    public_key: str
    creator_id: int
    receipt_id: int
    status: str
    payment_details: str | None
    receipt_comment: str | None
    created_at: datetime
    is_active: bool
