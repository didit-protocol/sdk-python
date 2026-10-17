"""The same calls on AsyncDidit, plus auto-pagination with ``async for``.

python examples/async_quickstart.py
"""

from __future__ import annotations

import asyncio
import os

from didit import AsyncDidit


async def main() -> None:
    async with AsyncDidit(base_url=os.environ.get("DIDIT_BASE_URL")) as client:
        session = await client.sessions.create(
            workflow_id=os.environ["DIDIT_WORKFLOW_ID"], vendor_data="user-123"
        )
        print("Session URL:", session.url)

        # Every session of the last week, across all pages.
        async for row in client.sessions.list(date_from="2026-10-10", limit=50):
            print(row.session_id, row.status)


if __name__ == "__main__":
    asyncio.run(main())
