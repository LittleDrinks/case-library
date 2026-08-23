from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator
from typing import BinaryIO, Protocol
from threading import Lock

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings


class BlobStore(Protocol):
    def health(self) -> None: ...

    def put(
        self, blob_id: str, source: BinaryIO, length: int, content_type: str
    ) -> None: ...

    def open(self, blob_id: str) -> Iterator[bytes]: ...

    def remove(self, blob_id: str) -> None: ...


class MinioBlobStore:
    def __init__(self, client: Minio, bucket: str):
        self.client = client
        self.bucket = bucket
        self._ready = False
        self._lock = Lock()

    def health(self) -> None:
        self._ensure_bucket()
        if not self.client.bucket_exists(self.bucket):
            raise OSError("object store bucket unavailable")

    def put(
        self, blob_id: str, source: BinaryIO, length: int, content_type: str
    ) -> None:
        self._ensure_bucket()
        self.client.put_object(
            self.bucket, self._object_key(blob_id), source, length, content_type
        )

    def open(self, blob_id: str) -> Iterator[bytes]:
        response = self.client.get_object(self.bucket, self._object_key(blob_id))
        return _response_chunks(response)

    def remove(self, blob_id: str) -> None:
        self.client.remove_object(self.bucket, self._object_key(blob_id))

    def _ensure_bucket(self) -> None:
        if self._ready:
            return
        with self._lock:
            if not self._ready:
                self._create_bucket()
                self._ready = True

    def _create_bucket(self) -> None:
        if self.client.bucket_exists(self.bucket):
            return
        try:
            self.client.make_bucket(self.bucket)
        except S3Error as error:
            if error.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise

    @staticmethod
    def _object_key(blob_id: str) -> str:
        return f"blobs/{blob_id}"


def _secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"secret file is empty: {path}")
    return value


def _response_chunks(response) -> Iterator[bytes]:
    try:
        yield from response.stream(1024 * 1024)
    finally:
        response.close()
        response.release_conn()


def minio_blob_store(settings: Settings) -> MinioBlobStore:
    client = Minio(
        settings.object_store_endpoint,
        access_key=_secret(settings.object_store_access_key_file),
        secret_key=_secret(settings.object_store_secret_key_file),
        secure=settings.object_store_secure,
    )
    return MinioBlobStore(client, settings.object_store_bucket)
