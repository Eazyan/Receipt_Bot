from domain.repositories.room_repository import RoomRepository
from domain.repositories.user_repository import UserRepository
from domain.entities.room import Room
import uuid
from datetime import datetime

class CreateRoomUseCase:
    def __init__(self, room_repository: RoomRepository, user_repository: UserRepository):
        self.room_repository = room_repository
        self.user_repository = user_repository

    def execute(self, creator_id: str, name: str) -> str:
        user = self.user_repository.get_by_id(creator_id)
        if user is None:
            raise ValueError(f"No such user with id {creator_id}")

        room_id = str(uuid.uuid4())

        room =  Room(
            id=room_id,
            name=name,
            creator_id=creator_id,
            created_at=datetime.now(),
            participants=[creator_id]
        )

        self.room_repository.save(room)
        return room_id