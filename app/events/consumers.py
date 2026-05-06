import json
from app.core.redpanda import get_consumer
from app.events.topics import REPLY_RECEIVED

def consume_reply_received(handler_fn):
    """Run this in a background thread. Calls handler_fn(distributor_id, parsed_reply_id)."""
    consumer = get_consumer("demand-agent-group")
    consumer.subscribe([REPLY_RECEIVED])
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None or msg.error():
                continue
            data = json.loads(msg.value().decode())
            handler_fn(data["distributor_id"], data["parsed_reply_id"])
    finally:
        consumer.close()