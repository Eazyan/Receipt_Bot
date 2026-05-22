from datetime import datetime
from decimal import Decimal
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Receipt, ReceiptItem, User
from app.api.schemas import ReceiptCreate, ReceiptItemCreate, ReceiptItemOut, ReceiptItemUpdate, ReceiptOut, ReceiptUpdate, ReceiptItemsResponse
from app.services.openrouter_ocr import OCRServiceError, item_price, item_quantity, parse_receipt_image
from app.services.receipt_assistant import ReceiptAssistantError, build_receipt_assistant_plan

router = APIRouter(prefix="/receipts", tags=["receipts"])
logger = logging.getLogger(__name__)


def _get_or_create_demo_user(db: Session) -> User:
    user = db.get(User, 1)
    if user:
        return user
    user = User(username="demo", user_public_name="Demo User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _parse_paid_at(date_value: str | None, time_value: str | None) -> datetime | None:
    if not date_value:
        return None

    raw = f"{date_value} {time_value or '00:00'}".strip()
    formats = (
        "%d.%m.%Y %H:%M",
        "%d.%m.%y %H:%M",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d/%m/%y %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _receipt_payload(receipt: Receipt) -> dict:
    items = [
        {
            "id": str(item.id),
            "name": item.name,
            "price": float(item.price),
            "quantity": float(item.quantity),
            "assignedUsers": [],
        }
        for item in receipt.items
    ]
    total_sum = sum(
        Decimal(str(item["price"])) * Decimal(str(item["quantity"]))
        for item in items
    )
    return {
        "id": str(receipt.id),
        "paidAt": receipt.paid_at.isoformat() if receipt.paid_at else receipt.created_at.isoformat(),
        "placeName": receipt.place_name,
        "tip": 0,
        "service": 0,
        "totalSum": float(total_sum),
        "items": items,
    }


def _apply_receipt_assistant_action(receipt: Receipt, action: dict, db: Session) -> None:
    action_type = action.get("type")

    if action_type == "update_item":
        item = db.get(ReceiptItem, int(action["itemId"]))
        if not item or item.receipt_id != receipt.id:
            return
        if "name" in action:
            item.name = str(action["name"])[:255]
        if "price" in action:
            item.price = Decimal(str(action["price"]))
        if "quantity" in action:
            item.quantity = Decimal(str(action["quantity"]))

    elif action_type == "add_item":
        db.add(ReceiptItem(
            receipt_id=receipt.id,
            name=str(action["name"])[:255],
            price=Decimal(str(action["price"])),
            quantity=Decimal(str(action.get("quantity", 1))),
        ))

    elif action_type == "delete_item":
        item = db.get(ReceiptItem, int(action["itemId"]))
        if item and item.receipt_id == receipt.id:
            db.delete(item)

    elif action_type == "merge_items":
        item_ids = [int(item_id) for item_id in action.get("itemIds", [])]
        items = [
            item for item_id in item_ids
            if (item := db.get(ReceiptItem, item_id)) and item.receipt_id == receipt.id
        ]
        if len(items) < 2:
            return
        total = sum((item.price * item.quantity for item in items), Decimal("0"))
        keeper = items[0]
        keeper.name = str(action.get("name") or keeper.name)[:255]
        keeper.price = total.quantize(Decimal("0.01"))
        keeper.quantity = Decimal("1")
        for item in items[1:]:
            db.delete(item)

    elif action_type == "split_item":
        item = db.get(ReceiptItem, int(action["itemId"]))
        split_items = action.get("items", [])
        if not item or item.receipt_id != receipt.id or not split_items:
            return
        first = split_items[0]
        item.name = str(first["name"])[:255]
        item.price = Decimal(str(first["price"]))
        item.quantity = Decimal(str(first.get("quantity", 1)))
        for next_item in split_items[1:]:
            db.add(ReceiptItem(
                receipt_id=receipt.id,
                name=str(next_item["name"])[:255],
                price=Decimal(str(next_item["price"])),
                quantity=Decimal(str(next_item.get("quantity", 1))),
            ))


@router.post("/", response_model=ReceiptOut, status_code=201)
def create_receipt(payload: ReceiptCreate, db: Session = Depends(get_db)):
    if not db.get(User, payload.creator_id):
        raise HTTPException(status_code=404, detail="Creator user not found")
    receipt = Receipt(**payload.model_dump())
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


@router.post("/parse", status_code=201)
async def parse_receipt_photo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image file")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image file is empty")

    try:
        parsed = parse_receipt_image(image_bytes)
    except OCRServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    creator = _get_or_create_demo_user(db)
    receipt = Receipt(
        creator_id=creator.id,
        paid_at=_parse_paid_at(parsed.date, parsed.time),
        place_name=parsed.store_name,
        status="draft",
    )
    db.add(receipt)
    db.flush()

    db_items = []
    for parsed_item in parsed.items:
        price = item_price(parsed_item)
        if not parsed_item.name or price < 0:
            continue
        db_items.append(
            ReceiptItem(
                receipt_id=receipt.id,
                name=parsed_item.name[:255],
                price=price,
                quantity=item_quantity(parsed_item),
            )
        )

    db.add_all(db_items)
    db.commit()
    db.refresh(receipt)
    return _receipt_payload(receipt)


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@router.post("/{receipt_id}/assistant")
def run_receipt_assistant(receipt_id: int, payload: dict, db: Session = Depends(get_db)):
    command = str(payload.get("command") or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Command is required")

    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    before_payload = _receipt_payload(receipt)
    try:
        plan = build_receipt_assistant_plan(before_payload, command)
    except ReceiptAssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info(
        "Receipt assistant command receipt_id=%s command=%r actions=%s message=%r",
        receipt_id,
        command,
        plan["actions"],
        plan["message"],
    )

    for action in plan["actions"]:
        _apply_receipt_assistant_action(receipt, action, db)

    db.commit()
    db.refresh(receipt)
    return {
        "message": plan["message"],
        "actions": plan["actions"],
        "receipt": _receipt_payload(receipt),
    }


@router.patch("/{receipt_id}", response_model=ReceiptOut)
def update_receipt(receipt_id: int, payload: ReceiptUpdate, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(receipt, field, value)
    db.commit()
    db.refresh(receipt)
    return receipt


@router.delete("/{receipt_id}", status_code=204)
def delete_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    db.delete(receipt)
    db.commit()


@router.get("/{receipt_id}/items", response_model=ReceiptItemsResponse)
def get_receipt_items(receipt_id: int, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return {"items": receipt.items}


@router.post("/{receipt_id}/items", status_code=201)
def add_receipt_item(receipt_id: int, payload: ReceiptItemCreate, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    item = ReceiptItem(receipt_id=receipt.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(receipt)
    return _receipt_payload(receipt)


@router.delete("/{receipt_id}/items/{item_id}")
def delete_receipt_item(receipt_id: int, item_id: int, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    item = db.get(ReceiptItem, item_id)
    if not item or item.receipt_id != receipt.id:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    db.commit()
    db.refresh(receipt)
    return _receipt_payload(receipt)


@router.put("/{receipt_id}/items/{item_id}")
@router.patch("/{receipt_id}/items/{item_id}")
def update_receipt_item(receipt_id: int, item_id: int, payload: ReceiptItemUpdate, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    item = db.get(ReceiptItem, item_id)
    if not item or item.receipt_id != receipt.id:
        raise HTTPException(status_code=404, detail="Item not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)

    db.commit()
    db.refresh(receipt)
    return _receipt_payload(receipt)
