#!/usr/bin/env python3
"""Migrate objects between S3-compatible backends with verification and resume safety."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class S3Location:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str


@dataclass(frozen=True, slots=True)
class ObjectState:
    key: str
    size: int
    etag: str | None


def _normalize_etag(value: Any) -> str | None:
    text = str(value or "").strip().strip('"').strip("'")
    return text or None


def _client_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            return str(error.get("Code") or "")
    return ""


def _load_boto3() -> Any:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised only in external runtime
        raise RuntimeError("boto3 is required to run object-storage migration") from exc
    return boto3


def build_s3_client(location: S3Location, *, boto3_module: Any | None = None) -> Any:
    boto3_module = boto3_module or _load_boto3()
    return boto3_module.client(
        "s3",
        endpoint_url=location.endpoint_url,
        region_name=location.region,
        aws_access_key_id=location.access_key_id,
        aws_secret_access_key=location.secret_access_key,
    )


def iter_object_states(client: Any, bucket: str, *, prefix: str = "") -> list[ObjectState]:
    states: list[ObjectState] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []) or []:
            key = str(item.get("Key") or "")
            if not key:
                continue
            states.append(
                ObjectState(
                    key=key,
                    size=int(item.get("Size") or 0),
                    etag=_normalize_etag(item.get("ETag")),
                )
            )
    return states


def head_object_state(client: Any, bucket: str, key: str) -> ObjectState | None:
    try:
        payload = client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _client_error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    return ObjectState(
        key=key,
        size=int(payload.get("ContentLength") or 0),
        etag=_normalize_etag(payload.get("ETag")),
    )


def ensure_bucket_exists(client: Any, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except Exception as exc:
        if _client_error_code(exc) not in {"404", "NoSuchBucket", "NotFound"}:
            raise
    client.create_bucket(Bucket=bucket)
    client.head_bucket(Bucket=bucket)


def object_is_current(source: ObjectState, destination: ObjectState | None) -> bool:
    if destination is None:
        return False
    if source.size != destination.size:
        return False
    if source.etag and destination.etag:
        return source.etag == destination.etag
    return True


def copy_object_with_verification(
    *,
    source_client: Any,
    source_bucket: str,
    source_state: ObjectState,
    target_client: Any,
    target_bucket: str,
) -> None:
    payload = source_client.get_object(Bucket=source_bucket, Key=source_state.key)
    body = payload["Body"]
    put_kwargs = {
        "Bucket": target_bucket,
        "Key": source_state.key,
        "Body": body,
    }
    if payload.get("ContentType"):
        put_kwargs["ContentType"] = payload["ContentType"]
    metadata = payload.get("Metadata") or {}
    if metadata:
        put_kwargs["Metadata"] = metadata
    try:
        target_client.put_object(**put_kwargs)
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()

    destination_state = head_object_state(target_client, target_bucket, source_state.key)
    if destination_state is None:
        raise RuntimeError(f"verification failed for {source_state.key}: destination object is missing")
    if destination_state.size != source_state.size:
        raise RuntimeError(
            f"verification failed for {source_state.key}: size {destination_state.size} != {source_state.size}"
        )
    if source_state.etag and destination_state.etag and source_state.etag != destination_state.etag:
        raise RuntimeError(
            f"verification failed for {source_state.key}: etag {destination_state.etag} != {source_state.etag}"
        )


def migrate_object_store(
    *,
    source_client: Any,
    source_bucket: str,
    target_client: Any,
    target_bucket: str,
    prefix: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_bucket_exists(target_client, target_bucket)
    summary: dict[str, Any] = {
        "ok": True,
        "source_bucket": source_bucket,
        "target_bucket": target_bucket,
        "prefix": prefix,
        "dry_run": dry_run,
        "total_objects": 0,
        "already_current": 0,
        "would_copy": 0,
        "copied": 0,
    }
    for source_state in iter_object_states(source_client, source_bucket, prefix=prefix):
        summary["total_objects"] += 1
        destination_state = head_object_state(target_client, target_bucket, source_state.key)
        if object_is_current(source_state, destination_state):
            summary["already_current"] += 1
            continue
        if dry_run:
            summary["would_copy"] += 1
            continue
        copy_object_with_verification(
            source_client=source_client,
            source_bucket=source_bucket,
            source_state=source_state,
            target_client=target_client,
            target_bucket=target_bucket,
        )
        summary["copied"] += 1
    return summary


def run_migration(
    *,
    source: S3Location,
    target: S3Location,
    prefix: str = "",
    dry_run: bool = False,
    boto3_module: Any | None = None,
) -> dict[str, Any]:
    source_client = build_s3_client(source, boto3_module=boto3_module)
    target_client = build_s3_client(target, boto3_module=boto3_module)
    return migrate_object_store(
        source_client=source_client,
        source_bucket=source.bucket,
        target_client=target_client,
        target_bucket=target.bucket,
        prefix=prefix,
        dry_run=dry_run,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-endpoint-url", required=True)
    parser.add_argument("--source-bucket", required=True)
    parser.add_argument("--source-region", default="us-east-1")
    parser.add_argument("--source-access-key-id", required=True)
    parser.add_argument("--source-secret-access-key", required=True)
    parser.add_argument("--target-endpoint-url", required=True)
    parser.add_argument("--target-bucket", required=True)
    parser.add_argument("--target-region", default="us-east-1")
    parser.add_argument("--target-access-key-id", required=True)
    parser.add_argument("--target-secret-access-key", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    summary = run_migration(
        source=S3Location(
            endpoint_url=args.source_endpoint_url,
            bucket=args.source_bucket,
            region=args.source_region,
            access_key_id=args.source_access_key_id,
            secret_access_key=args.source_secret_access_key,
        ),
        target=S3Location(
            endpoint_url=args.target_endpoint_url,
            bucket=args.target_bucket,
            region=args.target_region,
            access_key_id=args.target_access_key_id,
            secret_access_key=args.target_secret_access_key,
        ),
        prefix=args.prefix,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
