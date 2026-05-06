from confluent_kafka import Producer, Consumer, KafkaError
import os

BOOTSTRAP = os.getenv("REDPANDA_BROKER", "localhost:9092")

def get_producer() -> Producer:
    return Producer({"bootstrap.servers": BOOTSTRAP})

def get_consumer(group_id: str) -> Consumer:
    return Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": group_id,
        "auto.offset.reset": "earliest",
    })