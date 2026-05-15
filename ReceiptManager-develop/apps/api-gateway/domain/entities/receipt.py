from dataclasses import dataclass, field
from typing import List
from datetime import datetime
from decimal import Decimal


@dataclass
class ReceiptItem:
    """Сущность - позиция в чеке"""
    id: str
    name: str
    price: Decimal
    quantity: Decimal
    assigned_users: List[str] = field(default_factory=list)

    @property
    def total_price(self) -> Decimal:
        return self.price * self.quantity

    def assign_to_user(self, user_id: str) -> None:
        if user_id in self.assigned_users:
            raise ValueError("User already in assigned")
        self.assigned_users.append(user_id)

    def remove_assignment(self, user_id: str) -> None:
        if user_id in self.assigned_users:
            self.assigned_users.remove(user_id)


@dataclass
class Receipt:
    """Сущность Чек"""
    id: str
    paid_at: datetime
    items: List[ReceiptItem] = field(default_factory=list)

    @property
    def total_sum(self) -> Decimal:
        """Бизнес-правило: итоговая сумма зависит от позиций"""
        return sum([item.total_price for item in self.items], start=Decimal("0.00"))

    def add_item(self, name: str, price: Decimal, quantity: Decimal, item_id: str) -> None:
        """Бизнес-правило: в чеке не может быть двух одинаковых позиций"""

        if name in map(lambda x: x.name, self.items):
            raise ValueError(f"Position {name} already in receipt")
        if price < 0:
            raise ValueError("Price must be positive")
        item = ReceiptItem(
            id=item_id,
            name=name,
            price=price,
            quantity=quantity
        )
        self.items.append(item)
