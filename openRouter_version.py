import base64
import os
from openai import OpenAI

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

def image_to_data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

image_data_url = image_to_data_url("/Users/eazyan/Documents/ocr/test4.jpg")

prompt = """
You are extracting structured data from a Russian retail receipt photo.

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

Important extraction rules:
1. The receipt language is Russian.
2. Extract only actual purchased items.
3. Exclude service lines, bonuses, card balance, QR info, address, cashier, tax info, loyalty info.
4. Keep product names clean and human-readable.
5. Remove internal numeric article codes and prefixes such as 8737, 1140, 2718 if they are not part of the real product name.
6. Remove trailing garbage fragments like :24, :40, МГС:10, (РЕЖ, broken OCR suffixes, and obvious truncated service fragments if they are not part of the product name.
7. Preserve meaningful product details such as weight, fat percent, flavor, package size, and brand.
8. If quantity is shown as "1ШТ" or "1 шт", set quantity to 1.
9. For weighted goods like apples or crab sticks, quantity must be the weight in kg.
10. If a gift or promo item has price 0.00, include it as an item with line_total 0.00.
11. discount is the receipt-level discount amount, not per-item promo text.
12. total must be the final paid amount from the receipt.
13. If date or time are unreadable, use null.
14. All prices must be numbers, never strings.
15. Return valid JSON only.

Quality rules:
- Prefer correctness over completeness.
- If one character is unclear in a product name, still return the best cleaned name.
- Do not invent values not supported by the receipt.
"""

resp = client.chat.completions.create(
    model="qwen/qwen3.5-35b-a3b",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    ],
    max_tokens=2500,
    temperature=0.0,
    extra_body={
        "reasoning": {"effort": "none"},
        "provider": {"require_parameters": True}
    },
)

print(resp.choices[0].message.content)
