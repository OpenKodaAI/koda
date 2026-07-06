from __future__ import annotations

import hashlib
import io

from scripts.migrate_object_storage import migrate_object_store


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakePaginator:
    def __init__(self, client: FakeS3Client) -> None:
        self._client = client

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, object]]:
        bucket = self._client.storage.get(Bucket, {})
        contents = []
        for key, payload in sorted(bucket.items()):
            if not key.startswith(Prefix):
                continue
            contents.append(
                {
                    "Key": key,
                    "Size": len(payload["body"]),
                    "ETag": f'"{payload["etag"]}"',
                }
            )
        return [{"Contents": contents}]


class FakeS3Client:
    def __init__(self, storage: dict[str, dict[str, dict[str, object]]]) -> None:
        self.storage = storage

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_objects_v2"
        return FakePaginator(self)

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.storage:
            raise FakeClientError("404")

    def create_bucket(self, *, Bucket: str) -> None:
        self.storage.setdefault(Bucket, {})

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        try:
            payload = self.storage[Bucket][Key]
        except KeyError as exc:
            raise FakeClientError("404") from exc
        return {
            "ContentLength": len(payload["body"]),
            "ETag": f'"{payload["etag"]}"',
        }

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        payload = self.storage[Bucket][Key]
        return {
            "Body": io.BytesIO(payload["body"]),
            "ContentType": payload.get("content_type"),
            "Metadata": payload.get("metadata", {}),
        }

    def put_object(self, *, Bucket: str, Key: str, Body: object, **kwargs: object) -> None:
        self.storage.setdefault(Bucket, {})
        if hasattr(Body, "read"):
            body = Body.read()
        else:
            body = Body
        assert isinstance(body, (bytes, bytearray))
        body_bytes = bytes(body)
        self.storage[Bucket][Key] = {
            "body": body_bytes,
            "etag": hashlib.md5(body_bytes).hexdigest(),  # noqa: S324 - fixture only
            "content_type": kwargs.get("ContentType"),
            "metadata": kwargs.get("Metadata", {}),
        }


def _payload(text: str) -> dict[str, object]:
    body = text.encode("utf-8")
    return {
        "body": body,
        "etag": hashlib.md5(body).hexdigest(),  # noqa: S324 - fixture only
        "content_type": "text/plain",
        "metadata": {},
    }


def test_migrate_object_store_dry_run_reports_pending_copy() -> None:
    source = FakeS3Client({"source": {"prefix/file.txt": _payload("hello")}})
    target = FakeS3Client({"target": {}})

    summary = migrate_object_store(
        source_client=source,
        source_bucket="source",
        target_client=target,
        target_bucket="target",
        prefix="prefix/",
        dry_run=True,
    )

    assert summary["total_objects"] == 1
    assert summary["would_copy"] == 1
    assert summary["copied"] == 0
    assert target.storage["target"] == {}


def test_migrate_object_store_skips_matching_destination_objects() -> None:
    source = FakeS3Client({"source": {"a.txt": _payload("same"), "b.txt": _payload("new")}})
    target = FakeS3Client({"target": {"a.txt": _payload("same")}})

    summary = migrate_object_store(
        source_client=source,
        source_bucket="source",
        target_client=target,
        target_bucket="target",
    )

    assert summary["total_objects"] == 2
    assert summary["already_current"] == 1
    assert summary["copied"] == 1
    assert target.storage["target"]["b.txt"]["body"] == b"new"


def test_migrate_object_store_replaces_mismatched_destination_objects() -> None:
    source = FakeS3Client({"source": {"a.txt": _payload("fresh")}})
    target = FakeS3Client({"target": {"a.txt": _payload("stale")}})

    summary = migrate_object_store(
        source_client=source,
        source_bucket="source",
        target_client=target,
        target_bucket="target",
    )

    assert summary["copied"] == 1
    assert target.storage["target"]["a.txt"]["body"] == b"fresh"


def test_migrate_object_store_creates_missing_target_bucket() -> None:
    source = FakeS3Client({"source": {"a.txt": _payload("fresh")}})
    target = FakeS3Client({})

    summary = migrate_object_store(
        source_client=source,
        source_bucket="source",
        target_client=target,
        target_bucket="target",
    )

    assert summary["copied"] == 1
    assert "target" in target.storage
