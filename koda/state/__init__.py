"""Typed state-domain facades for runtime modules.

These facades let hot-path services depend on domain stores instead of a
monolithic persistence module, keeping the production path aligned with the
Postgres-first state model.
"""
