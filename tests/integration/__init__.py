"""Phase B.2 — multi-language integration tests.

Tests in this package spin up real Rust binaries via cargo and
exercise them through the Python gRPC clients. They are the only
tests that validate the proto contract end-to-end.

Auto-skipped when:
- Cargo is not on PATH (contributor without Rust toolchain).
- The bench wheel for ``koda-command-guard`` cannot be built (no
  matching python interpreter).
- Postgres fixture is unsatisfied (see ``tests/postgres_fixtures.py``).

Each test pays the binary build cost ONCE per session via the
``cargo_build_release`` fixture below, then reuses the resulting
binary path across all tests in this directory.
"""
