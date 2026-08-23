from __future__ import annotations

import os
from pathlib import Path


def _e2e_bucket() -> str:
    bucket = os.environ["OBJECT_STORE_BUCKET"]
    if not bucket.endswith("-e2e"):
        raise ValueError(f"refusing to clear non-E2E bucket: {bucket}")
    return bucket


def _secret(variable: str) -> str:
    path = os.environ[variable]
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"secret file is empty: {path}")
    return value


def _client():
    from minio import Minio

    return Minio(
        os.environ["OBJECT_STORE_ENDPOINT"],
        access_key=_secret("OBJECT_STORE_ACCESS_KEY_FILE"),
        secret_key=_secret("OBJECT_STORE_SECRET_KEY_FILE"),
        secure=os.getenv("OBJECT_STORE_SECURE", "false").lower() == "true",
    )


def clear_bucket(client, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        return
    for item in client.list_objects(bucket, recursive=True):
        client.remove_object(bucket, item.object_name)


def assert_bucket_empty(client, bucket: str) -> None:
    if any(client.list_objects(bucket, recursive=True)):
        raise RuntimeError(f"E2E bucket is not empty: {bucket}")


def main() -> None:
    bucket = _e2e_bucket()
    client = _client()
    clear_bucket(client, bucket)
    assert_bucket_empty(client, bucket)


if __name__ == "__main__":
    main()
