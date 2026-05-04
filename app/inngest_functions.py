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

from app.temporal.client import get_temporal_client
from app.temporal.workflow import DemandPlanningWorkflow

# ── Inngest client ─────────────────────────────────────────────────────────────
inngest_client = inngest.Inngest(
    app_id="demand-planning-agent",
    is_production=False,
)

FASTAPI_BASE = os.getenv("FASTAPI_BASE_URL", "http://fastapi:8000")


def _workflow_id(distributor_id: str) -> str:
    # Keep one long-running workflow per distributor per cycle.
    return f"demand-{distributor_id}-cycle"


async def _start_temporal_workflows_for_sent_emails(send_bulk_result: dict) -> dict:
    """
    After emails are sent, start waiting workflows in Temporal so they appear
    as RUNNING until distributors reply (or timeout after 7 days).
    """
    results = send_bulk_result.get("results", []) or []
    client = await get_temporal_client()

    started = []
    already_running = []
    failed = []

    for row in results:
        distributor_id = row.get("distributor_id")
        status = row.get("status")

        if not distributor_id or status != "success":
            continue

        wf_id = _workflow_id(distributor_id)
        try:
            await client.start_workflow(
                DemandPlanningWorkflow.run,
                distributor_id,
                id=wf_id,
                task_queue="demand-planning-queue",
            )
            started.append(wf_id)
        except Exception as exc:
            # temporalio exception classes differ across versions.
            # Treat "already started" as non-fatal and continue.
            if "already started" in str(exc).lower():
                already_running.append(wf_id)
            else:
                failed.append({"workflow_id": wf_id, "error": str(exc)})

    return {
        "started": started,
        "already_running": already_running,
        "failed": failed,
    }


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
    temporal_result = await step.run(
        "start-temporal-workflows",
        lambda: _start_temporal_workflows_for_sent_emails(result),
    )

    return {
        "status": "manual cycle triggered",
        "result": result,
        "temporal": temporal_result,
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
    temporal_result = await step.run(
        "start-temporal-workflows",
        lambda: _start_temporal_workflows_for_sent_emails(result),
    )

    return {
        "status": "monthly cycle triggered",
        "result": result,
        "temporal": temporal_result,
    }


# ── Export functions ───────────────────────────────────────────────────────────
inngest_functions = [demand_cycle_manual, demand_cycle_monthly]
