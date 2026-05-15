from dataclasses import dataclass
from datetime import datetime

@dataclass
class User:
    """Сущность Пользователь"""
    id: str
    username: str
    registered_at: datetime

