import json
import os
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError, field_validator


PROMPT = """
Ты AI-агент Telegram Mini App для разделения чека.

Твоя задача: понять команду пользователя и вернуть JSON-план действий для приложения.
Не объясняй рассуждения. Не используй markdown. Верни один raw JSON object.

Ты можешь делать только эти действия:

1. Забрать позицию текущему участнику:
{"type":"set_quantity","itemId":"...","quantity":number}

2. Забрать все доступные позиции текущему участнику:
{"type":"claim_all_available"}

3. Очистить выбор текущего участника:
{"type":"clear_participant"}

4. Предложить всем поделить весь чек поровну:
{"type":"propose_split","proposalType":"split_all_evenly","participantIds":["..."]}

5. Предложить всем поделить одну позицию:
{"type":"propose_split","proposalType":"split_item_evenly","itemId":"...","participantIds":["..."]}

6. Предложить конкретному участнику забрать позицию:
{"type":"propose_claim","itemId":"...","targetParticipantId":"...","quantity":number|null}

7. Принять или отклонить открытое предложение:
{"type":"accept_proposal","proposalId":"..."}
{"type":"decline_proposal","proposalId":"..."}

8. Изменить режим разделения, только если пользователь является создателем:
{"type":"set_split_mode","splitMode":"even|items|mixed"}

Правила:
- Используй только itemId, participantId и proposalId из контекста.
- Если пользователь пишет "мне", "себе", "я", используй текущего участника.
- Если пользователь пишет имя другого участника, выбери наиболее похожего участника по имени.
- Если команда вида "салфетки Маше", это обычно значит предложить Маше забрать салфетки.
- Если команда вида "кофе мне", это значит забрать кофе текущему участнику.
- Если команда вида "пиццу пополам", предложи поделить позицию между всеми участниками.
- Если команда вида "всё пополам", "делим поровну", предложи поделить весь чек между всеми участниками.
- Для весовых товаров можно выбрать дробное quantity. Если количество не указано, бери всю доступную часть позиции.
- Не трогай позиции, которые пользователь не назвал, кроме явных команд "всё себе", "весь чек поровну", "сбрось мой выбор".
- Если команда неясна, верни actions: [] и короткий вопрос/сообщение.
- Для опасных массовых действий без явного намерения верни actions: [].

Output schema:
{
  "message": "короткая фраза для пользователя",
  "actions": [
    {"type":"..."}
  ]
}
"""


ALLOWED_ACTION_TYPES = {
    "set_quantity",
    "claim_all_available",
    "clear_participant",
    "propose_split",
    "propose_claim",
    "accept_proposal",
    "decline_proposal",
    "set_split_mode",
}

ALLOWED_SPLIT_MODES = {"even", "items", "mixed"}
ALLOWED_PROPOSAL_TYPES = {"split_all_evenly", "split_item_evenly"}


class AssistantAction(BaseModel):
    type: str
    itemId: str | None = None
    quantity: float | None = None
    proposalType: str | None = None
    participantIds: list[str] = Field(default_factory=list)
    targetParticipantId: str | None = None
    proposalId: str | None = None
    splitMode: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        action_type = str(value or "").strip()
        if action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(f"Unsupported action type: {value}")
        return action_type


class AssistantPlan(BaseModel):
    message: str = ""
    actions: list[AssistantAction] = Field(default_factory=list)


class RoomAssistantError(RuntimeError):
    pass


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RoomAssistantError("AI returned non-JSON content")
        return json.loads(cleaned[start : end + 1])


def _participant_name(state: dict[str, Any], participant_id: str) -> str:
    for participant in state.get("participants", []):
        if str(participant.get("id")) == str(participant_id):
            return str(participant.get("name") or "участник")
    return "участник"


def _item_name(state: dict[str, Any], item_id: str) -> str:
    for item in state.get("items", []):
        if str(item.get("id")) == str(item_id):
            return str(item.get("name") or "позицию")
    return "позицию"


def _available_quantity(state: dict[str, Any], item_id: str, actor_participant_id: str) -> float:
    item = next((item for item in state.get("items", []) if str(item.get("id")) == str(item_id)), None)
    if not item:
        return 0.0
    total_quantity = float(item.get("quantity") or 0)
    splits = state.get("itemSplits", {}).get(str(item_id), {}) or {}
    actor_quantity = float(splits.get(actor_participant_id) or 0)
    allocated_by_others = sum(float(quantity or 0) for pid, quantity in splits.items() if str(pid) != actor_participant_id)
    return max(0.0, total_quantity - allocated_by_others + actor_quantity)


def _compact_context(state: dict[str, Any], actor_participant_id: str, command: str) -> dict[str, Any]:
    return {
        "command": command,
        "currentParticipantId": actor_participant_id,
        "currentParticipantName": _participant_name(state, actor_participant_id),
        "creatorParticipantId": str(state.get("creatorParticipantId") or ""),
        "splitMode": state.get("splitMode") or "items",
        "participants": [
            {
                "id": str(participant.get("id")),
                "name": str(participant.get("name") or ""),
            }
            for participant in state.get("participants", [])
        ],
        "items": [
            {
                "id": str(item.get("id")),
                "name": str(item.get("name") or ""),
                "price": float(item.get("price") or 0),
                "quantity": float(item.get("quantity") or 0),
                "availableForCurrentParticipant": _available_quantity(state, str(item.get("id")), actor_participant_id),
            }
            for item in state.get("items", [])
        ],
        "openProposals": [
            {
                "id": str(proposal.get("id")),
                "type": proposal.get("type"),
                "itemId": str(proposal.get("itemId")) if proposal.get("itemId") else None,
                "fromParticipantId": str(proposal.get("fromParticipantId") or ""),
                "targetParticipantId": str(proposal.get("targetParticipantId")) if proposal.get("targetParticipantId") else None,
                "participantIds": [str(pid) for pid in proposal.get("participantIds", [])],
                "status": proposal.get("status"),
            }
            for proposal in state.get("proposals", [])
            if proposal.get("status") == "open"
        ],
        "currentSplits": state.get("itemSplits", {}),
    }


def _call_openrouter(context: dict[str, Any]) -> AssistantPlan:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "replace_me":
        raise RoomAssistantError("OPENROUTER_API_KEY is not configured")

    model = (
        os.getenv("OPENROUTER_ROOM_ASSISTANT_MODEL")
        or os.getenv("OPENROUTER_INTELLIGENCE_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or "openai/gpt-4o-mini"
    )
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": _stable_json(context)},
            ],
            temperature=0.0,
            max_tokens=1800,
            extra_body={
                "reasoning": {"effort": "none"},
                "provider": {"require_parameters": True},
            },
        )
        return AssistantPlan.model_validate(_extract_json_object(response.choices[0].message.content or ""))
    except (OpenAIError, ValidationError, json.JSONDecodeError, RoomAssistantError) as exc:
        raise RoomAssistantError(f"AI command failed: {exc}") from exc


def _valid_ids(state: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    item_ids = {str(item.get("id")) for item in state.get("items", [])}
    participant_ids = {str(participant.get("id")) for participant in state.get("participants", [])}
    proposal_ids = {
        str(proposal.get("id"))
        for proposal in state.get("proposals", [])
        if proposal.get("status") == "open"
    }
    return item_ids, participant_ids, proposal_ids


def _normalize_actions(plan: AssistantPlan, state: dict[str, Any], actor_participant_id: str) -> list[dict[str, Any]]:
    item_ids, participant_ids, proposal_ids = _valid_ids(state)
    actor_participant_id = str(actor_participant_id)
    normalized: list[dict[str, Any]] = []

    for raw_action in plan.actions[:8]:
        action = raw_action.model_dump(exclude_none=True)
        action_type = action["type"]

        if action_type == "set_quantity":
            item_id = str(action.get("itemId") or "")
            if item_id not in item_ids:
                continue
            raw_quantity = action.get("quantity")
            quantity = _available_quantity(state, item_id, actor_participant_id) if raw_quantity is None else float(raw_quantity)
            normalized.append({
                "type": "set_quantity",
                "itemId": item_id,
                "quantity": max(0.0, min(quantity, _available_quantity(state, item_id, actor_participant_id))),
            })

        elif action_type in {"claim_all_available", "clear_participant"}:
            normalized.append({"type": action_type})

        elif action_type == "propose_split":
            proposal_type = str(action.get("proposalType") or "")
            if proposal_type not in ALLOWED_PROPOSAL_TYPES:
                continue
            participant_ids_raw = [str(pid) for pid in action.get("participantIds") or []]
            valid_participant_ids = [pid for pid in participant_ids_raw if pid in participant_ids]
            if actor_participant_id not in valid_participant_ids:
                valid_participant_ids.insert(0, actor_participant_id)
            if len(valid_participant_ids) < 2:
                continue
            next_action: dict[str, Any] = {
                "type": "propose_split",
                "proposalType": proposal_type,
                "fromParticipantId": actor_participant_id,
                "participantIds": valid_participant_ids,
            }
            item_id = str(action.get("itemId") or "")
            if proposal_type == "split_item_evenly":
                if item_id not in item_ids:
                    continue
                next_action["itemId"] = item_id
            normalized.append(next_action)

        elif action_type == "propose_claim":
            item_id = str(action.get("itemId") or "")
            target_id = str(action.get("targetParticipantId") or "")
            if item_id not in item_ids or target_id not in participant_ids or target_id == actor_participant_id:
                continue
            quantity = action.get("quantity")
            normalized.append({
                "type": "propose_claim",
                "itemId": item_id,
                "fromParticipantId": actor_participant_id,
                "targetParticipantId": target_id,
                "quantity": quantity,
            })

        elif action_type in {"accept_proposal", "decline_proposal"}:
            proposal_id = str(action.get("proposalId") or "")
            if proposal_id not in proposal_ids:
                continue
            normalized.append({
                "type": action_type,
                "proposalId": proposal_id,
                "participantId": actor_participant_id,
            })

        elif action_type == "set_split_mode":
            split_mode = str(action.get("splitMode") or "")
            if actor_participant_id != str(state.get("creatorParticipantId")) or split_mode not in ALLOWED_SPLIT_MODES:
                continue
            normalized.append({"type": "set_split_mode", "splitMode": split_mode})

    return normalized


def _default_message(actions: list[dict[str, Any]], state: dict[str, Any]) -> str:
    if not actions:
        return "Не понял команду. Напишите, какую позицию и кому назначить."
    first = actions[0]
    action_type = first.get("type")
    if action_type == "set_quantity":
        return f"Готово: {_item_name(state, str(first.get('itemId')))}."
    if action_type == "propose_claim":
        return f"Отправил запрос: {_item_name(state, str(first.get('itemId')))}."
    if action_type == "propose_split":
        return "Отправил предложение разделить."
    if action_type == "claim_all_available":
        return "Забрал доступные позиции."
    if action_type == "clear_participant":
        return "Сбросил ваш выбор."
    if action_type == "accept_proposal":
        return "Принял предложение."
    if action_type == "decline_proposal":
        return "Отклонил предложение."
    if action_type == "set_split_mode":
        return "Изменил режим разделения."
    return "Готово."


def build_room_assistant_plan(state: dict[str, Any], actor_participant_id: str, command: str) -> dict[str, Any]:
    clean_command = " ".join(str(command or "").split()).strip()
    if not clean_command:
        return {"message": "Напишите команду.", "actions": []}
    if not any(str(participant.get("id")) == str(actor_participant_id) for participant in state.get("participants", [])):
        raise RoomAssistantError("Participant is not in this room")

    context = _compact_context(state, str(actor_participant_id), clean_command)
    plan = _call_openrouter(context)
    actions = _normalize_actions(plan, state, str(actor_participant_id))
    message = " ".join((plan.message or "").split()).strip()[:240] or _default_message(actions, state)
    return {"message": message, "actions": actions}
