from datetime import datetime
from decimal import Decimal
from typing import List, Literal
from pydantic import BaseModel, ConfigDict, field_validator, computed_field, model_validator


"""Receipt schemas"""


class ReceiptCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    creator_id: int
    paid_at: datetime | None = None
    place_name: str | None = None
    status: Literal["parsing", "draft", "assigned", "archived"] = "parsing"

    @field_validator('status', mode='before')
    @classmethod
    def normalize_status(cls, v) -> str:
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("parsing", "draft", "assigned", "archived"):
                raise ValueError(f"Invalid status: {v}")
            return normalized
        raise ValueError(f"Invalid status type: {type(v)}")


class ReceiptUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    paid_at: datetime | None = None
    place_name: str | None = None
    status: Literal["parsing", "draft", "assigned", "archived"] | None = None

    @field_validator('status', mode='before')
    @classmethod
    def normalize_status(cls, v) -> str | None:
        if v is None:
            return v
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("parsing", "draft", "assigned", "archived"):
                raise ValueError(f"Invalid status: {v}")
            return normalized
        raise ValueError(f"Invalid status type: {type(v)}")



class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    paid_at: datetime | None
    place_name: str | None
    status: str
    created_at: datetime


"""User schemas"""


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


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str | None = None
    user_public_name: str | None = None


"""Room schemas"""


class RoomCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    public_key: str
    creator_id: int
    receipt_id: int
    status: Literal["active", "completed", "cancelled"] = "active"
    payment_details: str | None = None
    receipt_comment: str | None = None

    @field_validator('status', mode='before')
    @classmethod
    def normalize_status(cls, v) -> str:
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("active", "completed", "cancelled"):
                raise ValueError(f"Invalid status: {v}")
            return normalized
        raise ValueError(f"Invalid status type: {type(v)}")


class RoomUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    receipt_id: int | None = None
    status: Literal["active", "completed", "cancelled"] | None = None
    payment_details: str | None = None
    receipt_comment: str | None = None
    is_active: bool | None = None

    @field_validator('status', mode='before')
    @classmethod
    def normalize_status(cls, v) -> str | None:
        if v is None:
            return v
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("active", "completed", "cancelled"):
                raise ValueError(f"Invalid status: {v}")
            return normalized
        raise ValueError(f"Invalid status type: {type(v)}")


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


"""RoomParticipant schema"""


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    room_id: int
    user_id: int
    joined_at: datetime
    user: "UserOut"

    @computed_field
    @property
    def username(self) -> str:
        return self.user.username

    @computed_field
    @property
    def user_public_name(self) -> str | None:
        return self.user.user_public_name


"""ReceiptItem schema"""


class ReceiptItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_min_length=1)

    name: str
    price: Decimal
    quantity: Decimal = Decimal("1.000")

    @field_validator('price', 'quantity')
    @classmethod
    def validate_positive(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Must be non-negative")
        return v


class ReceiptItemUpdate(BaseModel):
    name: str | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None

    @field_validator('price', 'quantity')
    @classmethod
    def validate_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("Must be non-negative")
        return v


class ReceiptItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    name: str
    price: Decimal
    quantity: Decimal


class ReceiptItemsResponse(BaseModel):
    items: List[ReceiptItemOut]


"""ItemAssignment schema"""


class ItemAssignmentCreate(BaseModel):
    """Схема для создания назначения"""
    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: int
    user_id: int
    paid: Literal["not paid", "on review", "paid"] = "not paid"

    @field_validator('paid', mode='before')
    @classmethod
    def normalize_status(cls, v) -> str:
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("not paid", "on review", "paid"):
                raise ValueError(f"Invalid paid status: {v}")
            return normalized
        raise ValueError(f"Invalid paid status type: {type(v)}")


class ItemAssignmentUpdate(BaseModel):
    """Схема для обновления статуса оплаты"""
    model_config = ConfigDict(str_strip_whitespace=True)

    paid: Literal["not paid", "on review", "paid"]

    @field_validator('paid', mode='before')
    @classmethod
    def normalize_status(cls, v) -> str:
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("not paid", "on review", "paid"):
                raise ValueError(f"Invalid paid status: {v}")
            return normalized
        raise ValueError(f"Invalid paid status type: {type(v)}")


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    user_id: int
    paid: str
    username: str | None = None
    user_public_name: str | None = None
