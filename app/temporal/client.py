import os
from temporalio.client import Client


async def get_temporal_client() -> Client:
    return await Client.connect(os.getenv("TEMPORAL_HOST", "localhost:7233"))