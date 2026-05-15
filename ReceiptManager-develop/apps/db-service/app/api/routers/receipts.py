from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Receipt, ReceiptItem, User
from app.api.schemas import ReceiptCreate, ReceiptItemCreate, ReceiptItemOut, ReceiptItemUpdate, ReceiptOut, ReceiptUpdate, ReceiptItemsResponse
from app.services.openrouter_ocr import OCRServiceError, item_price, item_quantity, parse_receipt_image

router = APIRouter(prefix="/receipts", tags=["receipts"])


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
