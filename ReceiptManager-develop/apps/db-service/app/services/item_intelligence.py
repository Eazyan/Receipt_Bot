import asyncio
import hashlib
import json
import os
import re
from typing import Any, Literal

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.room_state import get_redis


ItemCategory = Literal["food", "drink", "alcohol", "delivery", "packaging", "discount", "other"]

CATEGORIES: set[str] = {"food", "drink", "alcohol", "delivery", "packaging", "discount", "other"}

PROMPT = """
You are a production classifier for Russian receipt items in a Telegram Mini App.

Return one raw JSON object only. Do not use markdown.

Categories:
- food: edible groceries, prepared meals, snacks, sauces, dairy, meat, fish, produce.
- drink: non-alcoholic drinks, water, coffee, tea, juice, soda.
- alcohol: beer, wine, spirits, cider, cocktails, alcoholic products.
- delivery: delivery, service, courier or platform fee lines.
- packaging: bags, disposable cups, lids, containers, packaging.
- discount: discount, coupon, promo, cashback or negative adjustment lines.
- other: non-food goods or uncertain items.

Rules:
1. Product names can contain OCR noise, abbreviations, brands, weights, slang, mixed Cyrillic/Latin and typos.
2. Do not rely on exact keyword matching. Infer the real product type from the whole name.
3. If unsure, use "other" with confidence below 0.55.
4. Suggestions must be personalized from the participant history only.
5. Suggest an item to the participant only when the current item is strongly semantically similar to something they previously selected.
6. Do not suggest by category alone. "Coffee" can match "капучино"; "cheese" can match "сыр"; but "bread" must not match "milk".
7. Handle rare names, brand-heavy names and OCR mistakes conservatively.

Output schema:
{
  "items": [
    {
      "id": "string",
      "category": "food|drink|alcohol|delivery|packaging|discount|other",
      "category_confidence": 0.0,
      "suggest_for_participant": true,
      "suggestion_confidence": 0.0,
      "matched_history_item": "string|null"
    }
  ]
}
"""


class IntelligenceItemInput(BaseModel):
    id: str
    name: str
    price: float
    quantity: float


class ParticipantHistoryItem(BaseModel):
    name: str
    category: ItemCategory = "other"
    count: int = 1

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_product_name(value)


class IntelligenceItemOutput(BaseModel):
    id: str
    category: ItemCategory = "other"
    category_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suggest_for_participant: bool = False
    suggestion_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_history_item: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        category = str(value or "other").strip().lower()
        return category if category in CATEGORIES else "other"


class IntelligenceResponse(BaseModel):
    items: list[IntelligenceItemOutput] = Field(default_factory=list)


def _clean_product_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:180]


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


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
            raise ValueError("OpenRouter returned non-JSON content")
        return json.loads(cleaned[start : end + 1])


def _history_key(participant_id: str) -> str:
    return f"participant:{participant_id}:item-history:v1"


def _intelligence_key(participant_id: str, items: list[dict[str, Any]], history: list[dict[str, Any]]) -> str:
    payload_hash = _hash_payload({"participantId": participant_id, "items": items, "history": history})
    return f"item-intelligence:v2:{payload_hash}"


async def load_participant_history(participant_id: str) -> list[dict[str, Any]]:
    raw = await get_redis().get(_history_key(participant_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [ParticipantHistoryItem.model_validate(item).model_dump() for item in data][:160]
    except (json.JSONDecodeError, ValidationError, TypeError):
        return []


async def remember_participant_items(participant_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = await load_participant_history(participant_id)
    by_name: dict[str, dict[str, Any]] = {
        item["name"].casefold(): dict(item)
        for item in previous
        if item.get("name")
    }

    for raw_item in items:
        if float(raw_item.get("quantity") or 0) <= 0:
            continue
        item = ParticipantHistoryItem(
            name=str(raw_item.get("name") or ""),
            category=str(raw_item.get("category") or "other"),
            count=1,
        )
        if not item.name:
            continue
        key = item.name.casefold()
        existing = by_name.get(key)
        if existing:
            existing["count"] = min(999, int(existing.get("count") or 1) + 1)
            if item.category != "other":
                existing["category"] = item.category
        else:
            by_name[key] = item.model_dump()

    next_history = sorted(by_name.values(), key=lambda entry: int(entry.get("count") or 1), reverse=True)[:160]
    await get_redis().set(_history_key(participant_id), json.dumps(next_history, ensure_ascii=False), ex=60 * 60 * 24 * 365)
    return next_history


def _fallback_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": str(item["id"]),
                "category": "other",
                "category_confidence": 0.0,
                "suggest_for_participant": False,
                "suggestion_confidence": 0.0,
                "matched_history_item": None,
            }
            for item in items
        ]
    }


def _call_openrouter(items: list[dict[str, Any]], history: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "replace_me":
        return _fallback_response(items)

    model = os.getenv("OPENROUTER_INTELLIGENCE_MODEL") or os.getenv("OPENROUTER_OCR_MODEL") or "openai/gpt-4o-mini"
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    payload = {
        "items": items,
        "participant_history": history,
    }
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": _stable_json(payload)},
        ],
        temperature=0.0,
        max_tokens=2200,
        extra_body={
            "reasoning": {"effort": "none"},
            "provider": {"require_parameters": True},
        },
    )
    return _extract_json_object(response.choices[0].message.content or "")


async def get_item_intelligence(participant_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    clean_items = [
        IntelligenceItemInput(
            id=str(item.get("id")),
            name=str(item.get("name") or ""),
            price=float(item.get("price") or 0),
            quantity=float(item.get("quantity") or 0),
        ).model_dump()
        for item in items
    ]
    history = await load_participant_history(participant_id)
    cache_key = _intelligence_key(participant_id, clean_items, history)
    cached = await get_redis().get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        raw_result = await asyncio.to_thread(_call_openrouter, clean_items, history)
        parsed = IntelligenceResponse.model_validate(raw_result)
    except (OpenAIError, ValidationError, json.JSONDecodeError, ValueError):
        parsed = IntelligenceResponse.model_validate(_fallback_response(clean_items))

    known_ids = {item["id"] for item in clean_items}
    by_id = {item.id: item for item in parsed.items if item.id in known_ids}
    result = {
        "items": [
            by_id.get(item["id"], IntelligenceItemOutput(id=item["id"])).model_dump()
            for item in clean_items
        ]
    }
    await get_redis().set(cache_key, json.dumps(result, ensure_ascii=False), ex=60 * 60 * 24)
    return result
