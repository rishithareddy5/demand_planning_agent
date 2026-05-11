from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.postal_webhook_controller import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


KNOWN_PAYLOAD = {
    "from": "revanbejagam@gmail.com",
    "subject": "Re: Demand Request",
    "plain_body": "MALKIST CHEESE 48 PCS X 72 - 100",
    "message_id": "msg-001",
    "in_reply_to": "original-001",
}


def test_webhook_valid_known_distributor_returns_200():
    with patch("app.controllers.postal_webhook_controller.parse_reply") as parse, \
         patch("app.controllers.postal_webhook_controller._emit_reply_received"), \
         patch("app.controllers.postal_webhook_controller._signal_temporal_workflow", new_callable=AsyncMock):
        parse.return_value = {"distributor_id": "D01", "reply_type": "demand", "confidence": 0.9, "items": [], "parsed_reply_id": 1}
        response = client.post("/webhook/reply", json=KNOWN_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["distributor_id"] == "D01"
    assert "parsed_data" in response.json()


def test_webhook_missing_from_and_invalid_json():
    assert client.post("/webhook/reply", json={"plain_body": "100"}).status_code == 400
    assert client.post("/webhook/reply", content="not json", headers={"Content-Type": "application/json"}).status_code == 400


def test_webhook_unknown_sender_returns_422():
    response = client.post("/webhook/reply", json={"from": "unknown@example.com", "plain_body": "MALKIST - 100"})
    assert response.status_code == 422


def test_webhook_redpanda_and_temporal_failures_do_not_break_request():
    with patch("app.controllers.postal_webhook_controller.parse_reply") as parse, \
         patch("app.controllers.postal_webhook_controller._emit_reply_received", side_effect=Exception("Kafka down")), \
         patch("app.controllers.postal_webhook_controller._signal_temporal_workflow", new_callable=AsyncMock, side_effect=Exception("Temporal down")):
        parse.return_value = {"distributor_id": "D01", "reply_type": "demand", "confidence": 0.9, "items": [], "parsed_reply_id": 1}
        response = client.post("/webhook/reply", json=KNOWN_PAYLOAD)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_validate_reply_activity_valid_and_invalid_paths():
    from app.temporal.activities import validate_reply_activity

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    cursor.fetchone.return_value = (1, "D01", "demand", 0.9)
    cursor.fetchall.return_value = [("SKU01", "MALKIST", 100), ("SKU04", "BENG BENG", 50)]

    with patch("app.temporal.activities.get_connection", return_value=conn):
        result = await validate_reply_activity(1)
    assert result["status"] == "valid"
    assert result["total_confirmed_qty"] == 150
    conn.close.assert_called_once()

    cursor.fetchone.return_value = None
    with patch("app.temporal.activities.get_connection", return_value=conn):
        result = await validate_reply_activity(999)
    assert result["status"] == "invalid"


@pytest.mark.asyncio
async def test_fetch_context_activity_success_and_not_found():
    from app.temporal.activities import fetch_context_activity

    db = MagicMock()
    service = MagicMock()
    service.execute.return_value = {"distributor_id": "D01", "historical_rows_count": 5, "unique_skus_purchased": 2}
    with patch("app.core.database.SessionLocal", return_value=db), \
         patch("app.services.fetch_distributor_context_service.FetchDistributorContextService", return_value=service):
        result = await fetch_context_activity("D01")
    assert result["distributor_id"] == "D01"
    db.close.assert_called_once()

    service.execute.side_effect = ValueError("Distributor not found")
    with patch("app.core.database.SessionLocal", return_value=db), \
         patch("app.services.fetch_distributor_context_service.FetchDistributorContextService", return_value=service):
        result = await fetch_context_activity("DXXX")
    assert result["status"] == "distributor_not_found"


@pytest.mark.asyncio
async def test_write_confirmed_and_confirmation_email_activities():
    from app.temporal.activities import send_confirmation_email_activity, write_confirmed_qty_activity

    validated = {"items": [{"sku_id": "SKU01", "sku_name": "MALKIST", "quantity": 11}], "total_confirmed_qty": 11}
    with patch("app.temporal.activities.write_confirmed_qty") as write:
        await write_confirmed_qty_activity("D01", validated)
    write.assert_called_once()

    with patch("app.services.send_demand_email_service.send_email", return_value={"status": "success"}) as send:
        result = await send_confirmation_email_activity("D01", validated)
    assert result["status"] == "success"
    send.assert_called_once()
