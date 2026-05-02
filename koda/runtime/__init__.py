"""Worker-side runtime helpers.

Modules here run inside the per-agent worker process (spawned by
:mod:`koda.control_plane.supervisor`). They wire the worker's Python
application to the various Rust services — currently the Phase 1B
bot-gateway consumer, with future runners (policy-engine acquire,
rpc-gateway pool) following the same module shape.
"""
