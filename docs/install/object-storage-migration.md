# Object storage migration

Use this guide only when migrating an existing installation that still uses MinIO as the embedded S3-compatible backend.

## Goal

Move objects from the old MinIO bucket to the new SeaweedFS bucket without changing the application's S3 contract.

## Recommended flow

1. Keep the old MinIO-backed stack available.
2. Start the new SeaweedFS-backed stack in parallel.
3. Run the migration script in dry-run mode first.
4. Run the real copy.
5. Validate object counts and representative reads.
6. Switch `KNOWLEDGE_V2_S3_ENDPOINT_URL` to the SeaweedFS endpoint.
7. Restart the stack.
8. Decommission MinIO only after the new stack is validated.

## Dry run

```bash
uv run python scripts/migrate_object_storage.py \
  --source-endpoint-url http://old-minio:9000 \
  --source-bucket koda-objects \
  --source-access-key-id <old-access-key> \
  --source-secret-access-key <old-secret> \
  --target-endpoint-url http://seaweedfs:8333 \
  --target-bucket koda-objects \
  --target-access-key-id <new-access-key> \
  --target-secret-access-key <new-secret> \
  --dry-run
```

## Copy

```bash
uv run python scripts/migrate_object_storage.py \
  --source-endpoint-url http://old-minio:9000 \
  --source-bucket koda-objects \
  --source-access-key-id <old-access-key> \
  --source-secret-access-key <old-secret> \
  --target-endpoint-url http://seaweedfs:8333 \
  --target-bucket koda-objects \
  --target-access-key-id <new-access-key> \
  --target-secret-access-key <new-secret>
```

## Notes

- The migration is resume-safe: existing destination objects with matching size and ETag are skipped.
- Use `--prefix` if you need to migrate only part of the bucket first.
- The script verifies copied objects by size and, when available on both sides, by ETag.
