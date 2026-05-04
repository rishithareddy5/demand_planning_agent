from fastapi import APIRouter, HTTPException, Request
from confluent_kafka import Producer
from temporalio.client import Client
import json
import os
import logging

from app.services.reply_parser_service import parse_reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Postal Webhook"])

# ── RedPanda config ────────────────────────────────────────────────────────────
REDPANDA_BROKER = os.getenv("REDPANDA_BROKER", "localhost:9092")
_producer = Producer({"bootstrap.servers": REDPANDA_BROKER})

# ── Temporal config ────────────────────────────────────────────────────────────
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _emit_reply_received(distributor_id: str, parsed_reply_id: int, from_address: str):
    """
    Publish ReplyReceived event to RedPanda.
    Any service subscribed to this topic (audit logger, analytics, etc.)
    will receive this automatically — no direct coupling needed.
    """
    payload = {
        "distributor_id": distributor_id,
        "parsed_reply_id": parsed_reply_id,
        "from_address": from_address,
    }
    _producer.produce(
        topic="ReplyReceived",
        key=distributor_id.encode(),
        value=json.dumps(payload).encode(),
    )
    _producer.flush()
    logger.info(f"[RedPanda] Emitted ReplyReceived for distributor={distributor_id}")


async def _signal_temporal_workflow(distributor_id: str, parsed_reply_id: int):
    """
    Signal the waiting Temporal workflow for this distributor.

    The workflow is already running and paused at:
        await wait_condition(lambda: self._reply_data is not None, timeout=7 days)

    This signal unblocks it and passes the parsed reply ID so it can
    proceed to validation → write → emit DemandConfirmed.

    Workflow ID convention: "demand-{distributor_id}"
    e.g. distributor D01 → workflow ID "demand-D01"
    """
    client = await Client.connect(TEMPORAL_HOST)

    workflow_id = f"demand-{distributor_id}"
    handle = client.get_workflow_handle(workflow_id)

    signal_payload = {
        "distributor_id": distributor_id,
        "parsed_reply_id": parsed_reply_id,
    }

    await handle.signal("reply_received", signal_payload)
    logger.info(f"[Temporal] Signalled workflow {workflow_id} with reply_id={parsed_reply_id}")


def _get_distributor_id_from_email(from_address: str) -> str | None:
    """
    Map the sender's Gmail address to a distributor_id.

    Your terminal output showed these mappings:
        revanbejagam@gmail.com  → D01
        rishithareddyc2002@gmail.com → D02  (also D04 in one row — check your data)
        poojithak493@gmail.com  → D05
        lingaphani21@gmail.com  → D04

    In production this should be a DB lookup:
        SELECT distributor_id FROM distributors WHERE email = $1
    For now it's a hardcoded map matching your test data.
    """
    EMAIL_TO_DISTRIBUTOR = {
        "revanbejagam@gmail.com":          "D01",
        "rishithareddyc2002@gmail.com":    "D02",
        "saherwardi.mustafa@gmail.com":    "D03",
        "lingaphani21@gmail.com":          "D04",
        "poojithak493@gmail.com":          "D05",
    }
    # Strip display name if present: "Revan <revan@gmail.com>" → "revan@gmail.com"
    if "<" in from_address:
        from_address = from_address.split("<")[1].strip(">").strip()

    return EMAIL_TO_DISTRIBUTOR.get(from_address.lower())


# ── Route ──────────────────────────────────────────────────────────────────────

@router.post("/webhook/reply")
async def postal_reply_webhook(request: Request):
    # ── 1. Parse incoming JSON ─────────────────────────────────────────────────
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    from_address = payload.get("from") or payload.get("from_address")
    subject      = payload.get("subject")
    plain_body   = payload.get("plain_body") or payload.get("text_body") or payload.get("body")
    message_id   = payload.get("message_id")
    in_reply_to  = payload.get("in_reply_to")

    if not from_address:
        raise HTTPException(status_code=400, detail="Missing from address")

    # ── 2. Resolve distributor_id from sender email ────────────────────────────
    distributor_id = _get_distributor_id_from_email(from_address)

    if not distributor_id:
        logger.warning(f"[Webhook] Unknown sender email: {from_address} — skipping")
        raise HTTPException(
            status_code=422,
            detail=f"No distributor mapped to email: {from_address}"
        )

    # ── 3. Parse the reply body (your existing logic — unchanged) ──────────────
    parsed_data = parse_reply(from_address, plain_body or "")

    # parsed_data contains the parsed SKU/qty rows.
    # Your ReplyParserService already saves to parsed_replies + parsed_reply_items.
    # We need the DB-assigned parsed_reply_id to pass to Temporal.
    parsed_reply_id = parsed_data.get("parsed_reply_id")  # adjust key to match your service's return

    # ── 4. Emit ReplyReceived to RedPanda ──────────────────────────────────────
    # This is fire-and-forget — even if Temporal is down, the event is saved
    # in RedPanda and can be replayed later.
    if parsed_reply_id:
        try:
            _emit_reply_received(distributor_id, parsed_reply_id, from_address)
        except Exception as e:
            # Don't fail the request if RedPanda is unreachable.
            # Log and continue — Temporal signal below is the critical path.
            logger.error(f"[RedPanda] Failed to emit ReplyReceived: {e}")

    # ── 5. Signal Temporal workflow ────────────────────────────────────────────
    # This unblocks the waiting DemandPlanningWorkflow for this distributor.
    # The workflow will proceed: validate → write confirmed qty → emit DemandConfirmed.
    if parsed_reply_id:
        try:
            await _signal_temporal_workflow(distributor_id, parsed_reply_id)
        except Exception as e:
            # Workflow may not be running yet (e.g. first-time setup).
            # Log the error but don't fail the webhook — reply is already parsed and saved.
            logger.error(f"[Temporal] Failed to signal workflow for {distributor_id}: {e}")

    # ── 6. Return response ─────────────────────────────────────────────────────
    return {
        "status": "received",
        "distributor_id": distributor_id,
        "from_address": from_address,
        "subject": subject,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "plain_body": plain_body,
        "parsed_data": parsed_data,
        "events_emitted": {
            "redpanda": "ReplyReceived" if parsed_reply_id else "skipped — no parsed_reply_id",
            "temporal": f"demand-{distributor_id}" if parsed_reply_id else "skipped — no parsed_reply_id",
        },
    }