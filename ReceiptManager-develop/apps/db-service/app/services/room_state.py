import json
import os
from copy import deepcopy
from decimal import Decimal
from typing import Any

import redis.asyncio as redis
from sqlalchemy.orm import Session, selectinload

from app.db.models import Receipt, Room


STATE_TTL_SECONDS = 60 * 60 * 24
PALETTE = ["#2F80ED", "#FFB020", "#19A974", "#8B5CF6", "#E5484D", "#00A3A3"]

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=True,
        )
    return _redis


def state_key(room_id: int) -> str:
    return f"room:{room_id}:state"


def channel_key(room_id: int) -> str:
    return f"room:{room_id}:events"


def _receipt_items(room: Room) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "price": float(item.price),
            "quantity": float(item.quantity),
        }
        for item in room.receipt.items
    ]


def _room_participants(room: Room) -> list[dict[str, str]]:
    participants = [
        {
            "id": str(participant.user_id),
            "name": participant.user.user_public_name or participant.user.username,
            "color": PALETTE[idx % len(PALETTE)],
        }
        for idx, participant in enumerate(room.participants)
    ]
    if participants:
        return participants
    return [
        {
            "id": str(room.creator_id),
            "name": room.creator.user_public_name or room.creator.username,
            "color": PALETTE[0],
        }
    ]


def load_room_with_receipt(db: Session, room_id: int) -> Room | None:
    return (
        db.query(Room)
        .where(Room.id == room_id)
        .options(
            selectinload(Room.receipt).selectinload(Receipt.items),
            selectinload(Room.creator),
            selectinload(Room.participants),
        )
        .first()
    )


def make_initial_state(room: Room) -> dict[str, Any]:
    return {
        "roomId": str(room.id),
        "version": 0,
        "creatorParticipantId": str(room.creator_id),
        "splitMode": "items",
        "participants": _room_participants(room),
        "items": _receipt_items(room),
        "itemSplits": {},
        "proposals": [],
        "updatedAt": None,
    }


async def get_room_state(db: Session, room_id: int) -> dict[str, Any] | None:
    client = get_redis()
    raw = await client.get(state_key(room_id))
    if raw:
        return json.loads(raw)

    room = load_room_with_receipt(db, room_id)
    if not room:
        return None

    state = make_initial_state(room)
    await client.set(state_key(room_id), json.dumps(state), ex=STATE_TTL_SECONDS)
    return state


def _quantity_by_item(state: dict[str, Any]) -> dict[str, Decimal]:
    return {
        str(item["id"]): Decimal(str(item.get("quantity", 0)))
        for item in state.get("items", [])
    }


def _participant_exists(state: dict[str, Any], participant_id: str) -> bool:
    return any(participant["id"] == participant_id for participant in state.get("participants", []))


def _actor_id(action: dict[str, Any]) -> str | None:
    raw_actor = action.get("actorParticipantId")
    if raw_actor is None or str(raw_actor).strip() == "":
        return None
    return str(raw_actor)


def _proposal_is_visible_to(proposal: dict[str, Any], participant_id: str | None) -> bool:
    if participant_id is None:
        return proposal.get("type") != "claim_item"
    if proposal.get("fromParticipantId") == participant_id:
        return True
    return participant_id in proposal.get("participantIds", [])


def public_state_for_participant(state: dict[str, Any], participant_id: str | None = None) -> dict[str, Any]:
    next_state = deepcopy(state)
    next_state["proposals"] = [
        proposal for proposal in next_state.get("proposals", [])
        if _proposal_is_visible_to(proposal, participant_id)
    ]
    return next_state


def _valid_participant_ids(state: dict[str, Any], raw_ids: list[Any]) -> list[str]:
    seen: set[str] = set()
    participant_ids: list[str] = []
    for raw_id in raw_ids:
        participant_id = str(raw_id)
        if participant_id in seen or not _participant_exists(state, participant_id):
            continue
        seen.add(participant_id)
        participant_ids.append(participant_id)
    return participant_ids


def _split_item_evenly(state: dict[str, Any], item_id: str, participant_ids: list[str]) -> None:
    quantities = _quantity_by_item(state)
    total_quantity = quantities.get(str(item_id), Decimal("0"))
    if total_quantity <= 0 or not participant_ids:
        return
    base = total_quantity / Decimal(len(participant_ids))
    split_map: dict[str, float] = {}
    allocated = Decimal("0")
    for index, participant_id in enumerate(participant_ids):
        quantity = total_quantity - allocated if index == len(participant_ids) - 1 else base
        split_map[participant_id] = float(quantity)
        allocated += quantity
    state.setdefault("itemSplits", {})[str(item_id)] = split_map


def _claim_item_for_participant(state: dict[str, Any], item_id: str, participant_id: str, raw_quantity: Any | None = None) -> None:
    quantities = _quantity_by_item(state)
    total_quantity = quantities.get(str(item_id), Decimal("0"))
    if total_quantity <= 0 or not _participant_exists(state, participant_id):
        return
    item_splits = dict(state.get("itemSplits", {}).get(str(item_id), {}))
    allocated_by_others = sum(
        Decimal(str(quantity))
        for split_participant_id, quantity in item_splits.items()
        if split_participant_id != participant_id
    )
    available = max(total_quantity - allocated_by_others, Decimal("0"))
    if available <= 0:
        return
    desired = available if raw_quantity is None else min(max(Decimal(str(raw_quantity)), Decimal("0")), available)
    if desired > 0:
        item_splits[participant_id] = float(desired)
        state.setdefault("itemSplits", {})[str(item_id)] = item_splits


def _apply_accepted_proposal(state: dict[str, Any], proposal: dict[str, Any]) -> None:
    participant_ids = _valid_participant_ids(state, proposal.get("participantIds", []))
    if proposal.get("type") == "claim_item" and proposal.get("itemId") and proposal.get("targetParticipantId"):
        _claim_item_for_participant(
            state,
            str(proposal["itemId"]),
            str(proposal["targetParticipantId"]),
            proposal.get("quantity"),
        )
    elif len(participant_ids) < 2:
        return
    elif proposal.get("type") == "split_item_evenly" and proposal.get("itemId"):
        _split_item_evenly(state, str(proposal["itemId"]), participant_ids)
    elif proposal.get("type") == "split_all_evenly":
        for item in state.get("items", []):
            _split_item_evenly(state, str(item["id"]), participant_ids)


def _clean_item_splits(state: dict[str, Any]) -> None:
    max_quantities = _quantity_by_item(state)
    cleaned: dict[str, dict[str, float]] = {}
    participant_ids = {participant["id"] for participant in state.get("participants", [])}

    for item_id, splits in state.get("itemSplits", {}).items():
        max_qty = max_quantities.get(str(item_id), Decimal("0"))
        remaining = max_qty
        next_splits: dict[str, float] = {}
        for participant_id, raw_quantity in splits.items():
            if participant_id not in participant_ids or remaining <= 0:
                continue
            quantity = min(max(Decimal(str(raw_quantity)), Decimal("0")), remaining)
            if quantity > 0:
                next_splits[participant_id] = float(quantity)
                remaining -= quantity
        if next_splits:
            cleaned[str(item_id)] = next_splits

    state["itemSplits"] = cleaned


def _apply_action(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    next_state = deepcopy(state)
    action_type = action.get("type")
    actor_id = _actor_id(action)

    if action_type == "set_quantity":
        item_id = str(action["itemId"])
        participant_id = actor_id or str(action["participantId"])
        quantity = max(Decimal(str(action.get("quantity", 0))), Decimal("0"))
        if actor_id and str(action.get("participantId", actor_id)) != actor_id:
            return next_state
        if not _participant_exists(next_state, participant_id):
            return next_state
        item_splits = dict(next_state.get("itemSplits", {}).get(item_id, {}))
        item_splits[participant_id] = float(quantity)
        next_state.setdefault("itemSplits", {})[item_id] = item_splits

    elif action_type == "set_item_map":
        if actor_id:
            return next_state
        item_id = str(action["itemId"])
        quantities = {
            str(participant_id): float(max(Decimal(str(quantity)), Decimal("0")))
            for participant_id, quantity in action.get("participantQuantities", {}).items()
            if _participant_exists(next_state, str(participant_id))
        }
        if quantities:
            next_state.setdefault("itemSplits", {})[item_id] = quantities
        else:
            next_state.setdefault("itemSplits", {}).pop(item_id, None)

    elif action_type == "set_state":
        if actor_id:
            return next_state
        next_state["itemSplits"] = action.get("itemSplits", {})

    elif action_type == "set_split_mode":
        if actor_id != str(next_state.get("creatorParticipantId")):
            return next_state
        split_mode = str(action.get("splitMode"))
        if split_mode in {"even", "items", "mixed"}:
            next_state["splitMode"] = split_mode

    elif action_type == "claim_all_available":
        if not actor_id or not _participant_exists(next_state, actor_id):
            return next_state
        for item in next_state.get("items", []):
            _claim_item_for_participant(next_state, str(item["id"]), actor_id)

    elif action_type == "clear_participant":
        participant_id = actor_id or str(action.get("participantId"))
        if not _participant_exists(next_state, participant_id):
            return next_state
        for item_splits in next_state.get("itemSplits", {}).values():
            item_splits.pop(participant_id, None)

    elif action_type == "add_participant":
        if actor_id:
            return next_state
        name = str(action.get("name", "")).strip()
        if name:
            participant_id = str(action.get("participantId") or f"guest-{len(next_state.get('participants', [])) + 1}")
            if not _participant_exists(next_state, participant_id):
                next_state.setdefault("participants", []).append(
                    {
                        "id": participant_id,
                        "name": name[:32],
                        "color": action.get("color") or PALETTE[len(next_state.get("participants", [])) % len(PALETTE)],
                    }
                )

    elif action_type == "upsert_participant":
        name = str(action.get("name", "")).strip()
        participant_id = str(action.get("participantId"))
        if actor_id and actor_id != participant_id:
            return next_state
        if name and participant_id:
            participants = next_state.setdefault("participants", [])
            for participant in participants:
                if participant["id"] == participant_id:
                    participant["name"] = name[:32]
                    participant["color"] = action.get("color") or participant.get("color") or PALETTE[0]
                    break
            else:
                participants.append(
                    {
                        "id": participant_id,
                        "name": name[:32],
                        "color": action.get("color") or PALETTE[len(participants) % len(PALETTE)],
                    }
                )

    elif action_type == "remove_participant":
        participant_id = str(action.get("participantId"))
        if actor_id and actor_id != participant_id:
            return next_state
        if len(next_state.get("participants", [])) > 1:
            next_state["participants"] = [
                participant for participant in next_state.get("participants", [])
                if participant["id"] != participant_id
            ]
            for item_splits in next_state.get("itemSplits", {}).values():
                item_splits.pop(participant_id, None)

    elif action_type == "clear":
        if actor_id:
            return next_state
        next_state["itemSplits"] = {}
        next_state["proposals"] = [
            {**proposal, "status": "declined"}
            for proposal in next_state.get("proposals", [])
            if proposal.get("status") == "open"
        ]

    elif action_type == "propose_split":
        proposal_type = str(action.get("proposalType"))
        from_participant_id = actor_id or str(action.get("fromParticipantId"))
        participant_ids = _valid_participant_ids(next_state, action.get("participantIds", []))
        if actor_id and str(action.get("fromParticipantId", actor_id)) != actor_id:
            return next_state
        if (
            proposal_type in {"split_all_evenly", "split_item_evenly"}
            and _participant_exists(next_state, from_participant_id)
            and from_participant_id in participant_ids
            and len(participant_ids) >= 2
        ):
            proposal_id = str(action.get("proposalId") or f"proposal-{int(state.get('version', 0)) + 1}")
            proposal = {
                "id": proposal_id,
                "type": proposal_type,
                "itemId": str(action.get("itemId")) if action.get("itemId") else None,
                "fromParticipantId": from_participant_id,
                "participantIds": participant_ids,
                "acceptedBy": [from_participant_id],
                "declinedBy": [],
                "status": "open",
                "createdAt": action.get("updatedAt"),
            }
            if proposal_type == "split_all_evenly" or proposal["itemId"]:
                next_state.setdefault("proposals", []).append(proposal)

    elif action_type == "propose_claim":
        item_id = str(action.get("itemId"))
        from_participant_id = actor_id or str(action.get("fromParticipantId"))
        target_participant_id = str(action.get("targetParticipantId"))
        if actor_id and str(action.get("fromParticipantId", actor_id)) != actor_id:
            return next_state
        if (
            item_id
            and _participant_exists(next_state, from_participant_id)
            and _participant_exists(next_state, target_participant_id)
            and from_participant_id != target_participant_id
        ):
            proposal_id = str(action.get("proposalId") or f"proposal-{int(state.get('version', 0)) + 1}")
            next_state.setdefault("proposals", []).append(
                {
                    "id": proposal_id,
                    "type": "claim_item",
                    "itemId": item_id,
                    "fromParticipantId": from_participant_id,
                    "targetParticipantId": target_participant_id,
                    "participantIds": [target_participant_id],
                    "acceptedBy": [],
                    "declinedBy": [],
                    "status": "open",
                    "quantity": action.get("quantity"),
                    "createdAt": action.get("updatedAt"),
                }
            )

    elif action_type == "accept_proposal":
        proposal_id = str(action.get("proposalId"))
        participant_id = actor_id or str(action.get("participantId"))
        if actor_id and str(action.get("participantId", actor_id)) != actor_id:
            return next_state
        for proposal in next_state.get("proposals", []):
            if proposal.get("id") != proposal_id or proposal.get("status") != "open":
                continue
            if participant_id not in proposal.get("participantIds", []):
                break
            accepted_by = proposal.setdefault("acceptedBy", [])
            if participant_id not in accepted_by:
                accepted_by.append(participant_id)
            proposal["declinedBy"] = [
                declined_id for declined_id in proposal.get("declinedBy", [])
                if declined_id != participant_id
            ]
            if set(proposal.get("participantIds", [])) <= set(accepted_by):
                proposal["status"] = "accepted"
                _apply_accepted_proposal(next_state, proposal)
            break

    elif action_type == "decline_proposal":
        proposal_id = str(action.get("proposalId"))
        participant_id = actor_id or str(action.get("participantId"))
        if actor_id and str(action.get("participantId", actor_id)) != actor_id:
            return next_state
        for proposal in next_state.get("proposals", []):
            if proposal.get("id") != proposal_id or proposal.get("status") != "open":
                continue
            if participant_id not in proposal.get("participantIds", []):
                break
            declined_by = proposal.setdefault("declinedBy", [])
            if participant_id not in declined_by:
                declined_by.append(participant_id)
            proposal["status"] = "declined"
            break

    _clean_item_splits(next_state)
    next_state["proposals"] = next_state.get("proposals", [])[-20:]
    next_state["version"] = int(state.get("version", 0)) + 1
    next_state["updatedAt"] = action.get("updatedAt")
    return next_state


async def apply_room_action(db: Session, room_id: int, action: dict[str, Any], viewer_participant_id: str | None = None) -> dict[str, Any] | None:
    client = get_redis()
    async with client.lock(f"room:{room_id}:lock", timeout=3, blocking_timeout=1):
        state = await get_room_state(db, room_id)
        if state is None:
            return None

        next_state = _apply_action(state, action)
        encoded = json.dumps(next_state)
        await client.set(state_key(room_id), encoded, ex=STATE_TTL_SECONDS)
        await client.publish(channel_key(room_id), encoded)
        return public_state_for_participant(next_state, viewer_participant_id)
