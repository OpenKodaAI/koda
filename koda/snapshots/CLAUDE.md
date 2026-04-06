# Environment Snapshots Guide

Save and restore agent environment state.

## Key Files
- `capture.py` -- Collect state from subsystems (filesystem, browser, processes, webhooks, workflows)
- `store.py` -- SnapshotStore (save/load/list/delete/diff)

## Snapshot Contents
- Working directory file listing
- Browser session metadata
- Background process list
- Webhook registrations
- Workflow definitions
