"""Worker-side runtime helpers.

Modules here run inside the per-agent worker process (spawned by
:mod:`koda.control_plane.supervisor`). They wire the worker's Python
application to the Rust sidecar services (bot-gateway consumer,
policy-engine acquire, and direct gRPC target pools with process-local
breakers).
"""
