import asyncio
import os
from temporalio.client import Client
from temporalio.worker import Worker
from app.temporal.workflow import DemandPlanningWorkflow
from app.temporal.activities import (
    fetch_context_activity,
    validate_reply_activity,
    write_confirmed_qty_activity,
    send_confirmation_email_activity,
    emit_demand_confirmed_activity,
)


async def main():
    client = await Client.connect(os.getenv("TEMPORAL_HOST", "temporal:7233"))
    worker = Worker(
        client,
        task_queue="demand-planning-queue",
        workflows=[DemandPlanningWorkflow],
        activities=[
            fetch_context_activity,
            validate_reply_activity,
            write_confirmed_qty_activity,
            send_confirmation_email_activity,
            emit_demand_confirmed_activity,
        ],
    )
    print("Worker started on queue: demand-planning-queue")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())