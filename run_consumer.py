import asyncio
from app.events.consumers import consume_reply_received
from app.temporal.client import get_temporal_client
from app.temporal.workflow import DemandPlanningWorkflow


async def handle_reply(distributor_id: str, parsed_reply_id: int):
    client = await get_temporal_client()
    workflow_id = f"demand-{distributor_id}-{parsed_reply_id}"

    try:
        # Start the workflow
        handle = await client.start_workflow(
            DemandPlanningWorkflow.run,
            distributor_id,
            id=workflow_id,
            task_queue="demand-planning-queue",
        )
        print(f"Temporal workflow started → distributor={distributor_id} reply_id={parsed_reply_id}")
    except Exception:
        # Workflow already exists — get the handle
        handle = client.get_workflow_handle(workflow_id)
        print(f"Workflow already exists → {workflow_id}")

    # Send the reply signal to unblock the wait_condition
    await handle.signal(
        DemandPlanningWorkflow.reply_received,
        {"parsed_reply_id": parsed_reply_id, "distributor_id": distributor_id}
    )
    print(f"Signal sent → workflow={workflow_id}")


def handler(distributor_id: str, parsed_reply_id: int):
    asyncio.run(handle_reply(distributor_id, parsed_reply_id))


if __name__ == "__main__":
    print("Consumer started — waiting for ReplyReceived events...")
    consume_reply_received(handler)