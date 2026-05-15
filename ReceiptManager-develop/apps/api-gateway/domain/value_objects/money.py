from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "RUB"

    def __add__(self, other):
        if not isinstance(other, Money) or self.currency != other.currency:
            raise ValueError("Can only add Money with same currency")
        return Money(self.amount + other.amount, self.currency)