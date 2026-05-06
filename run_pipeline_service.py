"""
run_pipeline_service.py

Gmail poller that runs forever inside Docker as a service.
Replaces running run_pipeline.py manually in a terminal.

What it does every POLL_INTERVAL_SECONDS (default 5 min):
  1. Loads SKU master data (primary sales + 30 recommended products)
  2. Reads unseen replies from Gmail IMAP
  3. Parses each reply (plain text body OR Excel attachment)
  4. Saves parsed reply to PostgreSQL
  5. Emits ReplyReceived event to RedPanda
  6. RedPanda consumer signals the Temporal workflow
  7. Temporal validates → writes confirmed_demands → sends confirmation email

Runs alongside:
  - temporal_worker  (registers and executes the workflow)
  - fastapi          (API layer)
  Everything starts automatically with: docker-compose up
"""

import os
import time
import threading
import asyncio
from pprint import pprint
from dotenv import load_dotenv

load_dotenv()

from read_replies import read_unseen_replies
from save_to_postgres import save_parsed_reply
from app.services.reply_parser_service import parse_reply
from app.services.attachment_parser_service import parse_excel_file, is_excel_attachment
from app.data.sku_data import load_sku_data
from app.events.producers import emit_reply_received
from app.events.consumers import consume_reply_received
from app.temporal.client import get_temporal_client
from app.temporal.workflow import DemandPlanningWorkflow

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
PRIMARY_SALES_FILE = "sample_data/Primary_Sales.xlsx"
RECOMMENDED_PRODUCTS_FILE = "sample_data/30_Recommended_New_Products.xlsx"


# ── Temporal signal handler ────────────────────────────────────────────────────

async def signal_temporal_async(distributor_id: str, parsed_reply_id: int):
    """
    Starts a new Temporal workflow for this distributor (if not already running),
    then sends it the reply_received signal so it can validate and confirm.
    """
    client = await get_temporal_client()
    workflow_id = f"demand-{distributor_id}-cycle"

    try:
        await client.start_workflow(
            DemandPlanningWorkflow.run,
            distributor_id,
            id=workflow_id,
            task_queue="demand-planning-queue",
        )
        print(f"[Temporal] Workflow started → {workflow_id}")
    except Exception:
        print(f"[Temporal] Workflow already running → {workflow_id}")

    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(
        DemandPlanningWorkflow.reply_received,
        {"parsed_reply_id": parsed_reply_id, "distributor_id": distributor_id}
    )
    print(f"[Temporal] Signal sent → reply_id={parsed_reply_id}")


def signal_temporal(distributor_id: str, parsed_reply_id: int):
    asyncio.run(signal_temporal_async(distributor_id, parsed_reply_id))


# ── RedPanda consumer (background thread) ─────────────────────────────────────

def on_reply_received(distributor_id: str, parsed_reply_id: int):
    """Called by RedPanda consumer for each ReplyReceived event."""
    print(f"[RedPanda] ReplyReceived → distributor={distributor_id} reply_id={parsed_reply_id}")
    signal_temporal(distributor_id, parsed_reply_id)


def start_redpanda_consumer():
    print("[RedPanda] Consumer started — listening for ReplyReceived events...")
    try:
        consume_reply_received(on_reply_received)
    except Exception as e:
        print(f"[RedPanda] Consumer error: {e}")


# ── Reply merging ──────────────────────────────────────────────────────────────

def merge_attachment_items(parsed_data: dict, attachment_items: list) -> dict:
    """
    Excel attachment takes priority over plain text body.
    Items from both are merged, deduplicating by sku_id.
    """
    if not attachment_items:
        return parsed_data

    text_items = parsed_data.get("items", []) or []
    final_items = []
    excel_sku_ids = set()

    for item in attachment_items:
        final_items.append(item)
        if item.get("sku_id"):
            excel_sku_ids.add(item["sku_id"])

    for item in text_items:
        if item.get("sku_id") and item["sku_id"] not in excel_sku_ids:
            final_items.append(item)

    parsed_data["items"] = final_items
    parsed_data["reply_type"] = "demand"
    parsed_data["needs_followup"] = False
    parsed_data["notes"] = "Excel attachment used as primary source."
    if parsed_data.get("confidence", 0) < 0.95:
        parsed_data["confidence"] = 0.95

    return parsed_data


# ── Main poll cycle ────────────────────────────────────────────────────────────

def run_one_poll_cycle():
    print("\n" + "=" * 70)
    print("[Poller] Loading SKU master data...")
    try:
        load_sku_data(
            primary_sales_file=PRIMARY_SALES_FILE,
            recommended_products_file=RECOMMENDED_PRODUCTS_FILE
        )
        print("[Poller] SKU data loaded")
    except Exception as e:
        print(f"[Poller] SKU data load failed: {e}")
        return

    print("[Poller] Reading Gmail inbox for distributor replies...")
    try:
        emails = read_unseen_replies()
    except Exception as e:
        print(f"[Poller] Gmail read failed: {e}")
        return

    if not emails:
        print("[Poller] No new replies found.")
        return

    print(f"[Poller] Found {len(emails)} new reply(s)")

    for index, item in enumerate(emails, start=1):
        print(f"\n--- Email #{index} ---")
        print(f"From:    {item['from_email']}")
        print(f"Subject: {item['subject']}")
        print(f"Body preview: {item['body'][:300]}")
        print(f"Attachments: {item.get('attachment_paths', [])}")

        # Parse plain text body
        parsed = parse_reply(
            from_email=item["from_email"],
            body=item["body"]
        )

        # Parse any Excel attachments
        attachment_items = []
        for path in item.get("attachment_paths", []):
            if is_excel_attachment(path):
                print(f"[Poller] Parsing attachment: {path}")
                try:
                    excel_items = parse_excel_file(path)
                    print(f"[Poller] Parsed {len(excel_items)} items from Excel")
                    attachment_items.extend(excel_items)
                except Exception as e:
                    print(f"[Poller] Excel parse error: {e}")

        parsed = merge_attachment_items(parsed, attachment_items)

        print("[Poller] Final parsed output:")
        pprint(parsed)

        # Save to PostgreSQL
        saved_id = save_parsed_reply(raw_email=item, parsed_data=parsed)

        # Only trigger pipeline for new demand replies
        if saved_id is not None and parsed.get("reply_type") == "demand":
            print(f"[Poller] Emitting ReplyReceived → distributor={parsed['distributor_id']} id={saved_id}")
            try:
                emit_reply_received(
                    distributor_id=parsed["distributor_id"],
                    parsed_reply_id=saved_id
                )
                print("[Poller] RedPanda event emitted ✓")
            except Exception as e:
                print(f"[Poller] RedPanda emit failed: {e}")
                # Fallback: signal Temporal directly without RedPanda
                print("[Poller] Falling back to direct Temporal signal...")
                try:
                    signal_temporal(parsed["distributor_id"], saved_id)
                except Exception as e2:
                    print(f"[Poller] Direct Temporal signal also failed: {e2}")
        elif saved_id is None:
            print("[Poller] Email already processed — skipping.")
        else:
            print(f"[Poller] Reply type is '{parsed.get('reply_type')}' — no event emitted.")

        if parsed.get("needs_followup"):
            print("[Poller] Follow-up required for this reply.")

    print("=" * 70)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("  Demand Planning Agent — Gmail Poller Service")
    print(f"  Poll interval: {POLL_INTERVAL} seconds ({POLL_INTERVAL // 60} minutes)")
    print("=" * 70)

    # Start RedPanda consumer in background thread
    consumer_thread = threading.Thread(target=start_redpanda_consumer, daemon=True)
    consumer_thread.start()
    print("[Service] RedPanda consumer thread started")

    # Give consumer a moment to connect
    time.sleep(3)

    # Poll Gmail forever
    while True:
        try:
            run_one_poll_cycle()
        except Exception as e:
            print(f"[Poller] Unexpected error in poll cycle: {e}")

        print(f"[Poller] Next poll in {POLL_INTERVAL // 60} minutes... (sleeping)")
        time.sleep(POLL_INTERVAL)