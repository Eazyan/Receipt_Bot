import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from app.db.database import SessionLocal, get_db
from app.db.models import ItemAssignment, Receipt, ReceiptItem, Room, RoomParticipant, User
from app.api.schemas import ParticipantOut, RoomCreate, RoomOut, RoomUpdate
from app.api.routers.receipts import _receipt_payload
from app.services.item_intelligence import get_item_intelligence, remember_participant_items
from app.services.room_assistant import RoomAssistantError, build_room_assistant_plan
from app.services.room_state import apply_room_action, channel_key, get_redis, get_room_state, public_state_for_participant

router = APIRouter(prefix="/rooms", tags=["rooms"])
logger = logging.getLogger(__name__)


@router.get("/{room_id}/state")
async def get_live_room_state(
    room_id: int,
    participant_id: str | None = Query(default=None, alias="participantId"),
    db: Session = Depends(get_db),
):
    state = await get_room_state(db, room_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return public_state_for_participant(state, participant_id)


@router.post("/{room_id}/state/actions")
async def apply_live_room_action(room_id: int, payload: dict, db: Session = Depends(get_db)):
    viewer_participant_id = payload.get("actorParticipantId") or payload.get("participantId")
    state = await apply_room_action(db, room_id, payload, str(viewer_participant_id) if viewer_participant_id else None)
    if state is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return state


@router.post("/{room_id}/assistant")
async def run_room_assistant(room_id: int, payload: dict, db: Session = Depends(get_db)):
    participant_id = str(payload.get("participantId") or payload.get("actorParticipantId") or "").strip()
    command = str(payload.get("command") or "").strip()
    if not participant_id:
        raise HTTPException(status_code=400, detail="participantId is required")
    if not command:
        raise HTTPException(status_code=400, detail="Command is required")

    state = await get_room_state(db, room_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        plan = build_room_assistant_plan(state, participant_id, command)
    except RoomAssistantError as exc:
        detail = str(exc)
        if "Participant is not in this room" in detail:
            raise HTTPException(status_code=403, detail=detail) from exc
        raise HTTPException(status_code=502, detail=detail) from exc

    logger.info(
        "Room assistant command room_id=%s participant_id=%s command=%r actions=%s message=%r",
        room_id,
        participant_id,
        command,
        plan["actions"],
        plan["message"],
    )

    next_state = public_state_for_participant(state, participant_id)
    for action in plan["actions"]:
        action = {
            **action,
            "actorParticipantId": participant_id,
            "updatedAt": payload.get("updatedAt"),
        }
        applied = await apply_room_action(db, room_id, action, participant_id)
        if applied is not None:
            next_state = applied

    return {
        "message": plan["message"],
        "actions": plan["actions"],
        "state": next_state,
    }


@router.get("/{room_id}/intelligence")
async def get_room_item_intelligence(
    room_id: int,
    participant_id: str = Query(alias="participantId"),
    db: Session = Depends(get_db),
):
    state = await get_room_state(db, room_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if not any(participant["id"] == participant_id for participant in state.get("participants", [])):
        raise HTTPException(status_code=403, detail="Participant is not in this room")
    return await get_item_intelligence(participant_id, state.get("items", []))


@router.post("/{room_id}/history")
async def remember_room_item_history(
    room_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    state = await get_room_state(db, room_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Room not found")

    participant_id = str(payload.get("participantId") or "")
    if not any(participant["id"] == participant_id for participant in state.get("participants", [])):
        raise HTTPException(status_code=403, detail="Participant is not in this room")

    categories_by_name = {
        str(item.get("name") or ""): str(item.get("category") or "other")
        for item in payload.get("items", [])
        if isinstance(item, dict)
    }
    items = []
    for item in state.get("items", []):
        quantity = float(state.get("itemSplits", {}).get(str(item.get("id")), {}).get(participant_id, 0) or 0)
        if quantity <= 0:
            continue
        name = str(item.get("name") or "")
        items.append({
            "name": name,
            "quantity": quantity,
            "category": categories_by_name.get(name, "other"),
        })
    history = await remember_participant_items(participant_id, items)
    return {"status": "ok", "count": len(history)}


@router.websocket("/{room_id}/ws")
async def room_state_ws(websocket: WebSocket, room_id: int):
    participant_id = websocket.query_params.get("participantId")
    await websocket.accept()

    db = SessionLocal()
    pubsub = None
    listener_task: asyncio.Task | None = None
    try:
        state = await get_room_state(db, room_id)
        if state is None:
            await websocket.close(code=1008)
            return

        await websocket.send_json({"type": "state", "state": public_state_for_participant(state, participant_id)})
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel_key(room_id))

        async def forward_updates():
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message["data"] if isinstance(message["data"], dict) else json.loads(message["data"])
                await websocket.send_json({"type": "state", "state": public_state_for_participant(data, participant_id)})

        listener_task = asyncio.create_task(forward_updates())

        while True:
            payload = await websocket.receive_json()
            viewer_participant_id = payload.get("actorParticipantId") or payload.get("participantId") or participant_id
            next_state = await apply_room_action(db, room_id, payload, str(viewer_participant_id) if viewer_participant_id else participant_id)
            if next_state is None:
                await websocket.send_json({"type": "error", "detail": "Room not found"})
    except WebSocketDisconnect:
        pass
    finally:
        if listener_task:
            listener_task.cancel()
        if pubsub:
            await pubsub.unsubscribe(channel_key(room_id))
            await pubsub.close()
        db.close()


@router.post("/", response_model=RoomOut, status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    if not db.get(User, payload.creator_id):
        raise HTTPException(status_code=404, detail="Creator user not found")
    if not db.get(Receipt, payload.receipt_id):
        raise HTTPException(status_code=404, detail="Receipt not found")
    room = Room(**payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    
    # Автоматически добавляем создателя в участники комнаты
    participant = RoomParticipant(room_id=room.id, user_id=payload.creator_id)
    db.add(participant)
    db.commit()
    
    return room


@router.get("/code/{public_key}")
def get_room_by_code(public_key: str, db: Session = Depends(get_db)):
    room = db.execute(
        select(Room).where(Room.public_key == public_key.upper()).options(
            selectinload(Room.receipt).selectinload(Receipt.items),
            selectinload(Room.participants).selectinload(RoomParticipant.user),
        )
    ).scalars().first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return {
        "id": room.id,
        "name": room.name,
        "public_key": room.public_key,
        "creator_id": room.creator_id,
        "receipt_id": room.receipt_id,
        "status": room.status,
        "payment_details": room.payment_details,
        "receipt_comment": room.receipt_comment,
        "created_at": room.created_at,
        "is_active": room.is_active,
        "receipt": _receipt_payload(room.receipt),
        "participants": [
            {
                "userId": str(participant.user_id),
                "username": participant.user.username,
                "firstName": participant.user.user_public_name or participant.user.username,
                "selected": {},
            }
            for participant in room.participants
        ],
    }


@router.get("/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.execute(
        select(Room).where(Room.id == room_id).options(
            selectinload(Room.participants).selectinload(RoomParticipant.user)
        )
    ).scalars().first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.patch("/{room_id}", response_model=RoomOut)
def update_room(room_id: int, payload: RoomUpdate, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=204)
def delete_room(room_id: int, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    db.delete(room)
    db.commit()


# ── Participants ──────────────────────────────────────────────────────────────

@router.get("/{room_id}/participants", response_model=list[ParticipantOut])
def list_participants(room_id: int, db: Session = Depends(get_db)):
    if not db.get(Room, room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    
    participants = db.execute(
        select(RoomParticipant)
        .where(RoomParticipant.room_id == room_id)
        .options(selectinload(RoomParticipant.user))
    ).scalars().all()
    return participants


@router.post("/{room_id}/participants/{user_id}", response_model=ParticipantOut, status_code=201)
def add_participant(room_id: int, user_id: int, db: Session = Depends(get_db)):
    if not db.get(Room, room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.get(RoomParticipant, (room_id, user_id))
    if existing:
        raise HTTPException(status_code=409, detail="User already in room")
    participant = RoomParticipant(room_id=room_id, user_id=user_id)
    db.add(participant)
    db.commit()
    db.refresh(participant, ["user"])
    return participant


@router.delete("/{room_id}/participants/{user_id}", status_code=204)
def remove_participant(room_id: int, user_id: int, db: Session = Depends(get_db)):
    participant = db.get(RoomParticipant, (room_id, user_id))
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    db.delete(participant)
    db.commit()


@router.post("/{room_id}/items/{item_id}/assign")
def assign_room_item(room_id: int, item_id: int, payload: dict, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    item = db.get(ReceiptItem, item_id)
    if not item or item.receipt_id != room.receipt_id:
        raise HTTPException(status_code=404, detail="Item not found")

    user_id = int(payload.get("userId") or payload.get("user_id") or room.creator_id)
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    assignment = db.get(ItemAssignment, (item_id, user_id))
    if not assignment:
        db.add(ItemAssignment(item_id=item_id, user_id=user_id, paid="not paid"))
    db.commit()
    return {"status": "ok"}
