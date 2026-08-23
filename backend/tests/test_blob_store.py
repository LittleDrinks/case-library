from __future__ import annotations

from app.modules.attachments.storage import MinioBlobStore


class BucketClient:
    def __init__(self) -> None:
        self.exists = False
        self.probes = 0

    def bucket_exists(self, _bucket: str) -> bool:
        self.probes += 1
        return self.exists

    def make_bucket(self, _bucket: str) -> None:
        self.exists = True


def test_health_creates_and_verifies_a_missing_bucket() -> None:
    client = BucketClient()

    MinioBlobStore(client, "case-library").health()

    assert client.exists is True
    assert client.probes == 2
