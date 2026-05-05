"""
app/inngest_functions.py

Inngest functions for the Demand Planning Agent.
Two functions:
  1. demand_cycle_monthly  - fires on 1st of every month at 9 AM
  2. demand_cycle_manual   - fires on demand/cycle.start event (manual trigger)
"""

import inngest
import httpx
import os

# ── Inngest client ─────────────────────────────────────────────────────────────
inngest_client = inngest.Inngest(
    app_id="demand-planning-agent",
    is_production=False,
)

FASTAPI_BASE = os.getenv("FASTAPI_BASE_URL", "http://fastapi:8000")


# ──────────────────────────────────────────────────────────────────────────────
# Function 1: Manual trigger (from Inngest UI / event)
# ──────────────────────────────────────────────────────────────────────────────
@inngest_client.create_function(
    fn_id="demand-cycle-manual",
    trigger=inngest.TriggerEvent(event="demand/cycle.start"),
)
async def demand_cycle_manual(ctx: inngest.Context) -> dict:
    """
    Fires when demand/cycle.start event is triggered manually.
    """

    step = ctx.step

    async def send_bulk_emails():
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{FASTAPI_BASE}/send-bulk")
            response.raise_for_status()
            return response.json()

    result = await step.run("send-bulk-emails", send_bulk_emails)

    return {
        "status": "manual cycle triggered",
        "result": result
    }


# ──────────────────────────────────────────────────────────────────────────────
# Function 2: Monthly cron trigger
# ──────────────────────────────────────────────────────────────────────────────
@inngest_client.create_function(
    fn_id="demand-cycle-monthly",
    trigger=inngest.TriggerCron(cron="0 9 1 * *"),
)
async def demand_cycle_monthly(ctx: inngest.Context) -> dict:
    """
    Automatically fires on 1st of every month at 9 AM.
    """

    step = ctx.step

    async def send_bulk_emails():
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{FASTAPI_BASE}/send-bulk")
            response.raise_for_status()
            return response.json()

    result = await step.run("send-bulk-emails", send_bulk_emails)

    return {
        "status": "monthly cycle triggered",
        "result": result
    }


# ── Export functions ───────────────────────────────────────────────────────────
inngest_functions = [demand_cycle_manual, demand_cycle_monthly]