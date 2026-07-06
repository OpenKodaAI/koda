"""Operator-facing CLI entry points.

Subcommands invoked by ``python -m koda <command>`` (e.g. ``migrate``)
live here. The default ``python -m koda`` entry point in
:mod:`koda.__main__` dispatches into this package when it sees a known
subcommand on ``sys.argv[1]`` so the existing ``--agent-id`` runtime
flow keeps working unchanged.
"""
