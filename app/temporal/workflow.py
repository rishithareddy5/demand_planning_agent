import asyncio
from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        fetch_context_activity,
        validate_reply_activity,
        write_confirmed_qty_activity,
        send_confirmation_email_activity,   # ← Fix: was missing from imports
        emit_demand_confirmed_activity,
    )


@workflow.defn
class DemandPlanningWorkflow:

    def __init__(self):
        self._reply_data: dict | None = None

    @workflow.run
    async def run(self, distributor_id: str):
        opts = {"start_to_close_timeout": timedelta(seconds=30)}

        # Fetch context
        await workflow.execute_activity(
            fetch_context_activity, distributor_id, **opts
        )

        # Wait for reply signal — timeout = 7 days
        try:
            await workflow.wait_condition(
                lambda: self._reply_data is not None,
                timeout=timedelta(days=7),
            )
        except asyncio.TimeoutError:
            workflow.logger.warning(
                f"No reply from {distributor_id} after 7 days — escalating"
            )
            return

        # Validate → write → confirm → emit
        reply_id = self._reply_data["parsed_reply_id"]

        validated = await workflow.execute_activity(
            validate_reply_activity, reply_id, **opts
        )

        if validated.get("status") == "valid":
            await workflow.execute_activity(
                write_confirmed_qty_activity,
                args=[distributor_id, validated],
                **opts,
            )
            # ── Fix: Send confirmation email back to the distributor ───────
            # This activity existed in activities.py and worker.py but was
            # never imported or called here — so no confirmation was ever sent.
            await workflow.execute_activity(
                send_confirmation_email_activity,
                args=[distributor_id, validated],
                **opts,
            )
            await workflow.execute_activity(
                emit_demand_confirmed_activity,
                args=[distributor_id, validated.get("total_confirmed_qty", 0)],
                **opts,
            )
        else:
            workflow.logger.warning(
                f"Validation failed for {distributor_id} "
                f"reply_id={reply_id} — sent to review queue"
            )

    @workflow.signal
    def reply_received(self, reply_data: dict):
        self._reply_data = reply_data