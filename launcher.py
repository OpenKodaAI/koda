"""Launch the dynamic control-plane supervisor."""

from __future__ import annotations

import asyncio

from koda.control_plane.supervisor import run_supervisor


def main() -> None:
    asyncio.run(run_supervisor())


if __name__ == "__main__":
    main()
