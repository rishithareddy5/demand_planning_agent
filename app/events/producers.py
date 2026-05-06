import json
from app.core.redpanda import get_producer
from app.events.topics import REPLY_RECEIVED, DEMAND_CONFIRMED

_producer = get_producer()

def emit_reply_received(distributor_id: str, parsed_reply_id: int):
    payload = {"distributor_id": distributor_id, "parsed_reply_id": parsed_reply_id}
    _producer.produce(REPLY_RECEIVED, key=distributor_id,
                      value=json.dumps(payload).encode())
    _producer.flush()

def emit_demand_confirmed(distributor_id: str, confirmed_qty: int):
    payload = {"distributor_id": distributor_id, "confirmed_qty": confirmed_qty}
    _producer.produce(DEMAND_CONFIRMED, key=distributor_id,
                      value=json.dumps(payload).encode())
    _producer.flush()