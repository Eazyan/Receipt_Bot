from dataclasses import dataclass, field
from typing import List
from datetime import datetime

@dataclass
class Room:
    """Сущность Комната"""
    id: str
    name: str
    creator_id: str
    created_at: datetime
    is_active: bool = True
    receipt_id: str | None = None
    participants: List[str] = field(default_factory=list) # user_ids

    def add_participant(self, user_id: str) -> None:
        """Бизнес-правило: нельзя дважды добавить пользователя"""
        if user_id in self.participants:
            raise ValueError("User already in room")
        self.participants.append(user_id)

    def can_finalize(self) -> bool:
        """Бизнес-правило: можно завершить если есть чек и участники"""
        return self.receipt_id is not None and len(self.participants) > 0
