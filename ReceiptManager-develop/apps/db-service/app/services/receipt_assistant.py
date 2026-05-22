import json
import os
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError, field_validator


PROMPT = """
Ты AI-агент для редактирования распознанного чека до создания комнаты.

Пользователь говорит коротко, неидеально и бытовым языком. Твоя задача:
понять, какие строки чека надо исправить, и вернуть JSON-план действий.
Не объясняй рассуждения. Не используй markdown. Верни один raw JSON object.

Контекст содержит items:
- id: ID строки
- name: текущее название
- unitPrice: цена за единицу
- quantity: количество/вес
- lineTotal: сумма строки = unitPrice * quantity

Действия:
1. Исправить строку:
{"type":"update_item","itemId":"...","name":"...","price":number,"quantity":number}
Можно указывать только поля, которые надо изменить.

2. Добавить строку:
{"type":"add_item","name":"...","price":number,"quantity":number}

3. Удалить строку:
{"type":"delete_item","itemId":"..."}

4. Объединить дубли:
{"type":"merge_items","itemIds":["...","..."],"name":"..."}
Если name не указан, выбери самое понятное название. Итоговая сумма объединенной строки должна быть суммой lineTotal, quantity = 1.

5. Разбить строку:
{"type":"split_item","itemId":"...","items":[{"name":"...","price":number,"quantity":number}]}
Первая новая строка заменит исходную, остальные будут добавлены.

Правила понимания:
- Используй только itemId из контекста.
- Команда может быть кривой ASR-расшифровкой голоса: слова могут быть похожи фонетически, с ошибками, без пунктуации, с перепутанными окончаниями.
- Перед выбором строки мысленно нормализуй команду по списку товаров из контекста. Например "абель сины", "опельсины" -> "апельсины"; "кехир" -> "кефир"; "покет" -> "пакет".
- Если есть одна явно ближайшая строка по звучанию и смыслу, редактируй её уверенно. Не требуй точного совпадения текста.
- Если пользователь называет товар приблизительно, выбери наиболее похожую строку.
- Если пользователь говорит "удали пакет", "убери доставку", "это лишнее" — delete_item.
- Если говорит "это не X, а Y", "переименуй X в Y" — update_item с name.
- Если говорит "X стоит 120", "у X сумма 120", "X должен быть 120" — обычно это lineTotal. Если quantity не 1, ставь price = сумма / quantity.
- Если говорит "цена за кг", "цена за штуку", "цена за единицу" — это unit price, ставь price напрямую.
- Если говорит "X 2 штуки", "количество X два", "вес X 0.372" — update_item quantity.
- Если говорит "добавь X за 50" — add_item с quantity 1, если количество не названо.
- Если говорит "два кофе по 150" — add/update quantity 2 price 150.
- Если говорит "объедини два X" или "дубли X" — merge_items.
- Если говорит "раздели строку X на A и B" — split_item.
- Не придумывай новые позиции без явной просьбы.
- Не меняй строки, которые пользователь не называл.
- Если команда неясна, верни actions: [] и короткий уточняющий вопрос.
- Округляй price до 2 знаков, quantity до 3 знаков.

Output schema:
{
  "message": "короткая фраза для пользователя",
  "actions": [
    {"type":"..."}
  ]
}
"""


ALLOWED_ACTION_TYPES = {"update_item", "add_item", "delete_item", "merge_items", "split_item"}


class ReceiptAssistantAction(BaseModel):
    type: str
    itemId: str | None = None
    itemIds: list[str] = Field(default_factory=list)
    name: str | None = None
    price: float | None = None
    quantity: float | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        action_type = str(value or "").strip()
        if action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(f"Unsupported action type: {value}")
        return action_type


class ReceiptAssistantPlan(BaseModel):
    message: str = ""
    actions: list[ReceiptAssistantAction] = Field(default_factory=list)


class ReceiptAssistantError(RuntimeError):
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
            raise ReceiptAssistantError("AI returned non-JSON content")
        return json.loads(cleaned[start : end + 1])


def _round_price(value: Any) -> float:
    return round(max(0.0, float(value)), 2)


def _round_quantity(value: Any) -> float:
    return round(max(0.001, float(value)), 3)


def _compact_context(receipt: dict[str, Any], command: str) -> dict[str, Any]:
    return {
        "command": command,
        "receipt": {
            "id": str(receipt.get("id") or ""),
            "placeName": receipt.get("placeName"),
            "totalSum": float(receipt.get("totalSum") or 0),
        },
        "items": [
            {
                "id": str(item.get("id")),
                "name": str(item.get("name") or ""),
                "unitPrice": float(item.get("price") or 0),
                "quantity": float(item.get("quantity") or 0),
                "lineTotal": round(float(item.get("price") or 0) * float(item.get("quantity") or 0), 2),
            }
            for item in receipt.get("items", [])
        ],
    }


def _call_openrouter(context: dict[str, Any]) -> ReceiptAssistantPlan:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "replace_me":
        raise ReceiptAssistantError("OPENROUTER_API_KEY is not configured")

    model = (
        os.getenv("OPENROUTER_RECEIPT_ASSISTANT_MODEL")
        or os.getenv("OPENROUTER_ROOM_ASSISTANT_MODEL")
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
            max_tokens=2200,
            extra_body={
                "reasoning": {"effort": "none"},
                "provider": {"require_parameters": True},
            },
        )
        return ReceiptAssistantPlan.model_validate(_extract_json_object(response.choices[0].message.content or ""))
    except (OpenAIError, ValidationError, json.JSONDecodeError, ReceiptAssistantError) as exc:
        raise ReceiptAssistantError(f"AI receipt edit failed: {exc}") from exc


def _item_name(receipt: dict[str, Any], item_id: str) -> str:
    for item in receipt.get("items", []):
        if str(item.get("id")) == item_id:
            return str(item.get("name") or "позицию")
    return "позицию"


def _valid_item_ids(receipt: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in receipt.get("items", [])}


def _normalize_actions(plan: ReceiptAssistantPlan, receipt: dict[str, Any]) -> list[dict[str, Any]]:
    item_ids = _valid_item_ids(receipt)
    normalized: list[dict[str, Any]] = []

    for raw_action in plan.actions[:8]:
        action = raw_action.model_dump(exclude_none=True)
        action_type = action["type"]

        if action_type == "update_item":
            item_id = str(action.get("itemId") or "")
            if item_id not in item_ids:
                continue
            next_action: dict[str, Any] = {"type": "update_item", "itemId": item_id}
            name = str(action.get("name") or "").strip()
            if name:
                next_action["name"] = name[:255]
            if "price" in action:
                next_action["price"] = _round_price(action["price"])
            if "quantity" in action:
                next_action["quantity"] = _round_quantity(action["quantity"])
            if len(next_action) > 2:
                normalized.append(next_action)

        elif action_type == "add_item":
            name = str(action.get("name") or "").strip()
            if not name or "price" not in action:
                continue
            normalized.append({
                "type": "add_item",
                "name": name[:255],
                "price": _round_price(action["price"]),
                "quantity": _round_quantity(action.get("quantity") or 1),
            })

        elif action_type == "delete_item":
            item_id = str(action.get("itemId") or "")
            if item_id in item_ids:
                normalized.append({"type": "delete_item", "itemId": item_id})

        elif action_type == "merge_items":
            merge_ids = []
            for raw_id in action.get("itemIds") or []:
                item_id = str(raw_id)
                if item_id in item_ids and item_id not in merge_ids:
                    merge_ids.append(item_id)
            if len(merge_ids) < 2:
                continue
            name = str(action.get("name") or "").strip()
            normalized.append({
                "type": "merge_items",
                "itemIds": merge_ids,
                **({"name": name[:255]} if name else {}),
            })

        elif action_type == "split_item":
            item_id = str(action.get("itemId") or "")
            split_items = []
            for raw_item in action.get("items") or []:
                name = str(raw_item.get("name") or "").strip()
                if not name or "price" not in raw_item:
                    continue
                split_items.append({
                    "name": name[:255],
                    "price": _round_price(raw_item["price"]),
                    "quantity": _round_quantity(raw_item.get("quantity") or 1),
                })
            if item_id in item_ids and split_items:
                normalized.append({"type": "split_item", "itemId": item_id, "items": split_items[:6]})

    return normalized


def _default_message(actions: list[dict[str, Any]], receipt: dict[str, Any]) -> str:
    if not actions:
        return "Не понял правку. Скажите, какую строку и что исправить."
    first = actions[0]
    action_type = first.get("type")
    if action_type == "update_item":
        return f"Исправил: {_item_name(receipt, str(first.get('itemId')))}."
    if action_type == "add_item":
        return f"Добавил: {first.get('name')}."
    if action_type == "delete_item":
        return f"Удалил: {_item_name(receipt, str(first.get('itemId')))}."
    if action_type == "merge_items":
        return "Объединил дубли."
    if action_type == "split_item":
        return f"Разбил строку: {_item_name(receipt, str(first.get('itemId')))}."
    return "Готово."


def build_receipt_assistant_plan(receipt: dict[str, Any], command: str) -> dict[str, Any]:
    clean_command = " ".join(str(command or "").split()).strip()
    if not clean_command:
        return {"message": "Напишите правку.", "actions": []}
    if not receipt.get("items"):
        return {"message": "В чеке нет строк для редактирования.", "actions": []}

    context = _compact_context(receipt, clean_command)
    plan = _call_openrouter(context)
    actions = _normalize_actions(plan, receipt)
    message = " ".join((plan.message or "").split()).strip()[:240] or _default_message(actions, receipt)
    return {"message": message, "actions": actions}
