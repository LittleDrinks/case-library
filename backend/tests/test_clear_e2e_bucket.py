from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import clear_e2e_bucket


class FakeMinio:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.removed: list[tuple[str, str]] = []

    def bucket_exists(self, _bucket: str) -> bool:
        return True

    def list_objects(self, _bucket: str, recursive: bool):
        assert recursive
        return [SimpleNamespace(object_name=name) for name in self.names]

    def remove_object(self, bucket: str, name: str) -> None:
        self.removed.append((bucket, name))


class ClearE2EBucketTests(unittest.TestCase):
    def test_cli_refuses_non_e2e_bucket(self) -> None:
        script = Path(clear_e2e_bucket.__file__)
        environment = os.environ | {"OBJECT_STORE_BUCKET": "case-library"}
        result = subprocess.run(
            [sys.executable, script], env=environment, capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to clear non-E2E bucket", result.stderr)

    def test_clear_bucket_removes_every_object(self) -> None:
        client = FakeMinio(["blobs/one", "imports/two"])
        clear_e2e_bucket.clear_bucket(client, "case-library-e2e")
        self.assertEqual(
            client.removed,
            [
                ("case-library-e2e", "blobs/one"),
                ("case-library-e2e", "imports/two"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
