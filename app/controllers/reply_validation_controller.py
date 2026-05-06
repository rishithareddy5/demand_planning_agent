from fastapi import APIRouter
from pydantic import BaseModel
import psycopg2
from app.core.database import get_connection

router = APIRouter(prefix="/reply-validation", tags=["Reply Validation"])


class ValidateRequest(BaseModel):
    parsed_reply_id: int


@router.get("/status")
def status():
    return {"status": "ok"}


@router.post("/validate")
def validate_reply(request: ValidateRequest):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Get the parsed reply
            cur.execute("""
                SELECT id, distributor_id, reply_type, confidence, needs_followup
                FROM parsed_replies
                WHERE id = %s
            """, (request.parsed_reply_id,))
            reply = cur.fetchone()

            if not reply:
                return {"status": "invalid", "reason": "Reply not found"}

            reply_id, distributor_id, reply_type, confidence, needs_followup = reply

            # Get the items
            cur.execute("""
                SELECT sku_id, sku_name, quantity
                FROM parsed_reply_items
                WHERE parsed_reply_id = %s
            """, (reply_id,))
            items = cur.fetchall()

            # Validation rules
            if reply_type != "demand":
                return {
                    "status": "invalid",
                    "reason": f"Reply type is {reply_type}, not demand",
                    "distributor_id": distributor_id,
                    "total_confirmed_qty": 0,
                    "items": []
                }

            if not items:
                return {
                    "status": "invalid",
                    "reason": "No items found in reply",
                    "distributor_id": distributor_id,
                    "total_confirmed_qty": 0,
                    "items": []
                }

            total_qty = sum(item[2] for item in items if item[2])

            return {
                "status": "valid",
                "distributor_id": distributor_id,
                "reply_type": reply_type,
                "confidence": float(confidence),
                "total_confirmed_qty": total_qty,
                "items": [
                    {"sku_id": i[0], "sku_name": i[1], "quantity": i[2]}
                    for i in items
                ]
            }

    finally:
        conn.close()