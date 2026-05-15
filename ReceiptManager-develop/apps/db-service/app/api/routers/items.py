from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.db.models import ItemAssignment, Receipt, ReceiptItem, User
from app.api.schemas import AssignmentOut, ReceiptItemCreate, ReceiptItemOut, ReceiptItemsResponse, ReceiptItemUpdate
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/{receipt_id}", response_model=ReceiptItemsResponse, status_code=201)
def create_items(
        receipt_id: int,
        payload: List[ReceiptItemCreate],
        db: Session = Depends(get_db)
):
    if not db.get(Receipt, receipt_id):
        logger.warning(f"Attempt to add items to nonexistent receipt_id: {receipt_id}")
        raise HTTPException(status_code=404, detail="Receipt not found")

    if not payload:
        logger.info(f"Empty payload was received for receipt_id: {receipt_id}. Skipping creation.")
        return {"items": []}

    items = [
        ReceiptItem(
            **item.model_dump(),
            receipt_id=receipt_id
        )
        for item in payload
    ]

    db.add_all(items)
    db.flush()
    db.commit()

    logger.info(f"Successfully added {len(items)} to receipt_id: {receipt_id}")

    return {"items": items}


@router.get("/{item_id}", response_model=ReceiptItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ReceiptItem, item_id)
    if not item:
        logger.warning(f"Attempt to get nonexistent item with item_id: {item_id}")
        raise HTTPException(status_code=404, detail="Item not found")
    logger.warning(f"Successfully get item with item_id: {item_id}")
    return item


@router.patch("/{item_id}", response_model=ReceiptItemOut)
def update_item(item_id: int, payload: ReceiptItemUpdate, db: Session = Depends(get_db)):
    item = db.get(ReceiptItem, item_id)
    if not item:
        logger.warning(f"Attempt to update nonexistent item with item_id: {item_id}")
        raise HTTPException(status_code=404, detail="Item not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    logger.warning(f"Successfully updated item with item_id: {item_id}")
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ReceiptItem, item_id)
    if not item:
        logger.warning(f"Attempt to delete nonexistent item with item_id: {item_id}")
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    logger.warning(f"Successfully deleted item with item_id: {item_id}")


# ── Assignments ───────────────────────────────────────────────────────────────

@router.get("/{item_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ReceiptItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    assignments_data = []
    for assignment in item.assignments:
        assignments_data.append({
            "item_id": assignment.item_id,
            "user_id": assignment.user_id,
            "paid": assignment.paid,
            "username": assignment.user.username,
            "user_public_name": assignment.user.user_public_name
        })
    return assignments_data


@router.post("/{item_id}/assignments/{user_id}", response_model=AssignmentOut, status_code=201)
def assign_item(item_id: int, user_id: int, paid: str = "not paid", db: Session = Depends(get_db)):
    if not db.get(ReceiptItem, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if db.get(ItemAssignment, (item_id, user_id)):
        raise HTTPException(status_code=409, detail="Assignment already exists")
    normalized_paid = paid.lower()
    if normalized_paid not in ("not paid", "on review", "paid"):
        raise HTTPException(status_code=400, detail=f"Invalid paid status: {paid}")
    assignment = ItemAssignment(item_id=item_id, user_id=user_id, paid=normalized_paid)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {
        "item_id": assignment.item_id,
        "user_id": assignment.user_id,
        "paid": assignment.paid,
        "username": user.username,
        "user_public_name": user.user_public_name
    }


@router.delete("/{item_id}/assignments/{user_id}", status_code=204)
def remove_assignment(item_id: int, user_id: int, db: Session = Depends(get_db)):
    assignment = db.get(ItemAssignment, (item_id, user_id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()


@router.patch("/{item_id}/assignments/{user_id}/paid", response_model=AssignmentOut)
def update_assignment_paid_status(item_id: int, user_id: int, paid: str, db: Session = Depends(get_db)):
    assignment = db.get(ItemAssignment, (item_id, user_id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    normalized_paid = paid.lower()
    if normalized_paid not in ("not paid", "on review", "paid"):
        raise HTTPException(status_code=400, detail=f"Invalid paid status: {paid}")
    assignment.paid = normalized_paid
    db.commit()
    db.refresh(assignment)
    return {
        "item_id": assignment.item_id,
        "user_id": assignment.user_id,
        "paid": assignment.paid,
        "username": assignment.user.username,
        "user_public_name": assignment.user.user_public_name
    }
