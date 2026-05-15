from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    user_message: str
    user_id: int
    receipt_id: int
    task_type: str # room or receipt
    room_id: int | None = None  # обязателен для task_type == "room"
    
    @field_validator('user_id', 'receipt_id', 'room_id', mode='before')
    @classmethod
    def convert_ids_to_int(cls, v):
        """Convert string IDs to integers, allowing both str and int inputs"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except (ValueError, TypeError) as e:
                raise ValueError(f"ID must be a valid integer, got: {v}") from e
        raise ValueError(f"ID must be an integer or string representation of integer, got type: {type(v).__name__}")


class CommandResult(BaseModel):
    id: str
    data: str


class Transcription(BaseModel):
    text: str
    language: str
# ──────────────────────────────
# User
# ──────────────────────────────

class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_min_length=1)

    username: str
    user_public_name: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    user_public_name: str | None
    registered_at: datetime


# ──────────────────────────────
# Receipt
# ──────────────────────────────

class ReceiptCreate(BaseModel):
    id: int
    paid_at: datetime


class ReceiptUpdate(BaseModel):
    paid_at: datetime | None = None


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paid_at: datetime


# ──────────────────────────────
# Room
# ──────────────────────────────

class RoomCreate(BaseModel):
    id: int
    name: str
    creator_id: int
    receipt_id: int | None = None


class RoomUpdate(BaseModel):
    name: str | None = None
    receipt_id: int | None = None
    is_active: bool | None = None


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    public_key: str
    creator_id: int
    receipt_id: int | None
    created_at: datetime
    is_active: bool


# ──────────────────────────────
# RoomParticipant
# ──────────────────────────────

class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    room_id: int
    user_id: int
    username: str
    user_public_name: str | None
    joined_at: datetime | None


# ──────────────────────────────
# ReceiptItem
# ──────────────────────────────

class ReceiptItemCreate(BaseModel):
    id: int
    receipt_id: int
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


# ──────────────────────────────
# ItemAssignment
# ──────────────────────────────

class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    user_id: int
    paid: str
    username: str | None = None
    user_public_name: str | None = None
