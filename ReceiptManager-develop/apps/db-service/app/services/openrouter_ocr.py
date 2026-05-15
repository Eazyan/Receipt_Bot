import base64
import json
import os
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openai import OpenAI, OpenAIError
from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel, Field, ValidationError, field_validator


PROMPT = """
You are extracting structured data from a Russian retail or restaurant receipt photo.

Task:
Read the receipt carefully and return ONE raw JSON object only.
Do not use markdown.
Do not wrap the answer in ```json fences.
Do not add explanations.

Output schema:
{
  "store_name": string | null,
  "date": string | null,
  "time": string | null,
  "items": [
    {
      "name": string,
      "quantity": number | null,
      "unit_price": number | null,
      "line_total": number | null
    }
  ],
  "discount": number | null,
  "total": number | null,
  "currency": "RUB"
}

Rules:
1. The receipt language is usually Russian.
2. Extract only actual purchased items.
3. Exclude service lines, bonuses, QR info, address, cashier, tax info, loyalty info, card balance.
4. Keep product names clean and human-readable.
5. Remove internal article codes and broken OCR fragments if they are not part of the product name.
6. Preserve meaningful details: weight, fat percent, flavor, package size, brand.
7. If quantity is shown as "1 шт", set quantity to 1.
8. If a receipt line contains quantity math like "2.000 X 42.90 = 85.80":
   - quantity = 2
   - unit_price = 42.90
   - line_total = 85.80
9. If a line contains "1.000 X 43.40" and then "43.40", quantity = 1, unit_price = 43.40, line_total = 43.40.
10. For weighted goods, quantity must be the weight in kg and unit_price must be price per kg.
11. If an item has price 0.00, include it.
12. Do not merge different receipt lines into one item.
13. discount is receipt-level discount amount.
14. total must be final paid amount from the receipt.
   The large "ИТОГ" line near the bottom is authoritative. Read this line especially carefully.
15. If date or time are unreadable, use null.
16. All prices must be numbers, never strings.
17. Return valid JSON only.

Quality rules:
- The image can be low resolution. Similar digits such as 5/6, 0/8, 1/7 are easy to confuse.
- Validate every price against the visible quantity math and the final "ИТОГ" line before answering.
- If item math and the final "ИТОГ" conflict, re-read the suspicious digit instead of inventing a new total.

Example:
Receipt text:
Батон Салютный нарезанный 30Г
1.000 X 43.40
43.40
Сырочка Алтайская доля 7
2.000 X 42.90
85.80
Output items:
[
  {"name":"Батон Салютный нарезанный 30Г","quantity":1,"unit_price":43.40,"line_total":43.40},
  {"name":"Сырочка Алтайская доля 7","quantity":2,"unit_price":42.90,"line_total":85.80}
]

Prefer correctness over completeness. Do not invent values not supported by the receipt.
"""


class ParsedOCRItem(BaseModel):
    name: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split()).strip()


class ParsedOCRReceipt(BaseModel):
    store_name: str | None = None
    date: str | None = None
    time: str | None = None
    items: list[ParsedOCRItem] = Field(default_factory=list)
    discount: Decimal | None = None
    total: Decimal | None = None
    currency: str = "RUB"


class OCRServiceError(RuntimeError):
    pass


def _decimal_or_default(value: Decimal | None, default: str) -> Decimal:
    if value is None:
        return Decimal(default)
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _crop_receipt_area(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size

    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            brightness = (r + g + b) / 3
            # Receipts are usually the brightest large object on a wooden/table background.
            if brightness > 145 and max(r, g, b) - min(r, g, b) < 70:
                xs.append(x)
                ys.append(y)

    if not xs or not ys:
        return image

    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    if (right - left) * (bottom - top) < width * height * 0.12:
        return image

    pad_x = max(8, int((right - left) * 0.04))
    pad_y = max(8, int((bottom - top) * 0.04))
    return image.crop((
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(width, right + pad_x),
        min(height, bottom + pad_y),
    ))


def _resize_for_ocr(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width < 1300:
        scale = 1300 / max(width, 1)
        image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    image.thumbnail((2000, 3000), Image.Resampling.LANCZOS)
    return image


def _image_to_data_url(image: Image.Image, quality: int = 92) -> str:
    out = BytesIO()
    image.save(out, format="JPEG", quality=quality, optimize=True)
    encoded = base64.b64encode(out.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _prepare_image_data_urls(image_bytes: bytes) -> list[str]:
    with Image.open(BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        cropped = _resize_for_ocr(_crop_receipt_area(image))
        enhanced = ImageOps.autocontrast(cropped).filter(ImageFilter.SHARPEN)
        grayscale = ImageOps.grayscale(cropped)
        contrast = ImageOps.autocontrast(grayscale, cutoff=1)
        threshold = contrast.point(lambda pixel: 255 if pixel > 165 else 0, mode="1").convert("RGB")

    return [_image_to_data_url(cropped), _image_to_data_url(enhanced), _image_to_data_url(threshold, quality=95)]


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
            raise OCRServiceError("OpenRouter returned non-JSON content")
        return json.loads(cleaned[start : end + 1])


def parse_receipt_image(image_bytes: bytes) -> ParsedOCRReceipt:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "replace_me":
        raise OCRServiceError("OPENROUTER_API_KEY is not configured")

    models_raw = os.getenv("OPENROUTER_OCR_MODELS") or os.getenv("OPENROUTER_OCR_MODEL") or "qwen/qwen3.5-35b-a3b,google/gemini-2.5-flash,openai/gpt-4o-mini"
    models = [model.strip() for model in models_raw.split(",") if model.strip()]
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    image_data_urls = _prepare_image_data_urls(image_bytes)
    content: list[dict[str, Any]] = [{"type": "text", "text": PROMPT}]
    for idx, image_data_url in enumerate(image_data_urls, 1):
        content.append({"type": "text", "text": f"Receipt image version {idx}."})
        content.append({"type": "image_url", "image_url": {"url": image_data_url}})

    best_candidate: ParsedOCRReceipt | None = None
    last_error: Exception | None = None

    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                max_tokens=3000,
                temperature=0.0,
                extra_body={
                    "reasoning": {"effort": "none"},
                    "provider": {"require_parameters": True},
                },
            )
            message_content = response.choices[0].message.content or ""
            candidate = ParsedOCRReceipt.model_validate(_extract_json_object(message_content))
            candidate = _reconcile_single_digit_price_error(candidate)
            if best_candidate is None:
                best_candidate = candidate
            if _receipt_totals_are_consistent(candidate):
                return candidate
            last_error = OCRServiceError(f"{model} returned inconsistent item totals")
        except (OpenAIError, ValidationError, json.JSONDecodeError, OCRServiceError) as exc:
            last_error = exc
            continue

    if best_candidate is not None:
        return best_candidate
    raise OCRServiceError(f"OpenRouter request failed: {last_error}") from last_error


def _receipt_totals_are_consistent(receipt: ParsedOCRReceipt) -> bool:
    if receipt.total is None or not receipt.items:
        return True

    item_sum = Decimal("0.00")
    for item in receipt.items:
        if item.line_total is not None:
            item_sum += item.line_total
        elif item.unit_price is not None:
            item_sum += item.unit_price * item_quantity(item)

    if item_sum <= 0:
        return False

    tolerance = max(Decimal("2.00"), abs(receipt.total) * Decimal("0.03"))
    return abs(item_sum - receipt.total) <= tolerance


def _line_total(item: ParsedOCRItem) -> Decimal:
    if item.line_total is not None:
        return item.line_total
    if item.unit_price is not None:
        return item.unit_price * item_quantity(item)
    return Decimal("0.00")


def _items_total(receipt: ParsedOCRReceipt) -> Decimal:
    return sum((_line_total(item) for item in receipt.items), Decimal("0.00"))


def _reconcile_single_digit_price_error(receipt: ParsedOCRReceipt) -> ParsedOCRReceipt:
    if receipt.total is None or len(receipt.items) < 2:
        return receipt

    current_total = _items_total(receipt)
    delta = (receipt.total - current_total).quantize(Decimal("0.01"))
    if abs(delta) not in {Decimal("10.00"), Decimal("20.00"), Decimal("30.00"), Decimal("40.00"), Decimal("50.00")}:
        return receipt

    for index, item in enumerate(receipt.items):
        quantity = item_quantity(item)
        if quantity <= 0:
            continue

        per_unit_delta = (delta / quantity).quantize(Decimal("0.01"))
        base_price = item.unit_price
        if base_price is None and item.line_total is not None:
            base_price = item.line_total / quantity
        if base_price is None:
            continue

        corrected_price = (base_price + per_unit_delta).quantize(Decimal("0.01"))
        corrected_line_total = (corrected_price * quantity).quantize(Decimal("0.01"))
        if corrected_price < 0 or corrected_line_total < 0:
            continue

        corrected_items = list(receipt.items)
        corrected_items[index] = item.model_copy(
            update={
                "unit_price": corrected_price,
                "line_total": corrected_line_total,
            }
        )
        corrected_receipt = receipt.model_copy(update={"items": corrected_items})
        if _receipt_totals_are_consistent(corrected_receipt):
            return corrected_receipt

    return receipt


def item_price(item: ParsedOCRItem) -> Decimal:
    if item.unit_price is not None:
        price = item.unit_price
    elif item.line_total is not None:
        qty = item_quantity(item)
        price = item.line_total / qty if qty > 0 else item.line_total
    else:
        price = None
    return _decimal_or_default(price, "0.00").quantize(Decimal("0.01"))


def item_quantity(item: ParsedOCRItem) -> Decimal:
    return _decimal_or_default(item.quantity, "1.000").quantize(Decimal("0.001"))
