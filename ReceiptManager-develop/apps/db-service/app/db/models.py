from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    user_public_name: Mapped[str | None] = mapped_column(String(64))
    registered_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(timezone.utc))

    created_rooms: Mapped[list["Room"]] = relationship(back_populates="creator", foreign_keys="Room.creator_id")
    room_participations: Mapped[list["RoomParticipant"]] = relationship(back_populates="user")
    item_assignments: Mapped[list["ItemAssignment"]] = relationship(back_populates="user")


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"))
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    place_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="parsing", nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(timezone.utc))

    creator: Mapped["User"] = relationship()
    rooms: Mapped[list["Room"]] = relationship(back_populates="receipt")
    items: Mapped[list["ReceiptItem"]] = relationship("ReceiptItem", back_populates="receipt",
                                                      cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"))
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="RESTRICT", onupdate="CASCADE"))
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    payment_details: Mapped[str | None] = mapped_column(String(256), nullable=True)
    receipt_comment: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(timezone.utc))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    creator: Mapped["User"] = relationship(back_populates="created_rooms", foreign_keys=[creator_id])
    receipt: Mapped["Receipt"] = relationship(back_populates="rooms")
    participants: Mapped[list["RoomParticipant"]] = relationship(back_populates="room", cascade="all, delete-orphan")


class RoomParticipant(Base):
    __tablename__ = "room_participants"

    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE", onupdate="CASCADE"),
                                         primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
                                         primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    room: Mapped["Room"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(back_populates="room_participations")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE", onupdate="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=Decimal("1.000"))

    receipt: Mapped["Receipt"] = relationship(back_populates="items")
    assignments: Mapped[list["ItemAssignment"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class ItemAssignment(Base):
    __tablename__ = "item_assignments"

    item_id: Mapped[int] = mapped_column(ForeignKey("receipt_items.id", ondelete="CASCADE", onupdate="CASCADE"),
                                         primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
                                         primary_key=True)
    paid: Mapped[str] = mapped_column(String(50), default="not paid", nullable=False)

    item: Mapped["ReceiptItem"] = relationship(back_populates="assignments")
    user: Mapped["User"] = relationship(back_populates="item_assignments")