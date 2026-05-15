from enum import Enum


class ReceiptStatusEnum(str, Enum):
    PARSING = "parsing"
    DRAFT = "draft"
    ASSIGNED = "assigned"
    ARCHIVED = "archived"


class RoomStatusEnum(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaidStatusEnum(str, Enum):
    NOT_PAID = "not paid"
    ON_REVIEW = "on review"
    PAID = "paid"