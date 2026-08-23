import os
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError


def primary_is_ready(uri: str) -> bool:
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2_000)
        return bool(client.admin.command("hello").get("isWritablePrimary"))
    except PyMongoError:
        return False


def wait_for_primary(uri: str, attempts: int = 60) -> None:
    for _ in range(attempts):
        if primary_is_ready(uri):
            return
        time.sleep(2)
    raise RuntimeError("MongoDB replica set has no writable primary")


wait_for_primary(os.environ["MONGODB_URI"])
