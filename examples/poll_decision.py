"""Poll a Didit session decision until it is final.

DIDIT_API_KEY=... python examples/poll_decision.py <session_id>

The async client has the same method; use ``await`` and ``asyncio.sleep``.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

import didit
from didit import Didit
from didit.types import SessionDecision

TERMINAL_STATUSES = frozenset({"Approved", "Declined", "Expired", "Kyc Expired", "Abandoned"})


def poll_decision(
    client: Didit,
    session_id: str,
    *,
    timeout: float = 300.0,
    initial_interval: float = 1.0,
    max_interval: float = 10.0,
    stop_on_review: bool = False,
    stop_when: Callable[[SessionDecision], bool] | None = None,
) -> SessionDecision:
    """Return the first decision that is final, or raise ``TimeoutError``.

    The loop uses a monotonic deadline, so wall-clock changes do not extend it.
    The interval doubles up to ``max_interval``; add jitter in production if
    many workers poll the same session.
    """
    deadline = time.monotonic() + timeout
    interval = initial_interval
    while True:
        decision = client.sessions.retrieve_decision(session_id)
        if decision.status in TERMINAL_STATUSES:
            return decision
        if stop_on_review and decision.status == "In Review":
            return decision
        if stop_when is not None and stop_when(decision):
            return decision
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"session {session_id} is still {decision.status!r}")
        time.sleep(min(interval, remaining))
        interval = min(max_interval, interval * 2)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python examples/poll_decision.py <session_id>")
    session_id = sys.argv[1]

    try:
        with Didit() as client:
            decision = poll_decision(client, session_id)
    except TimeoutError as err:
        raise SystemExit(str(err)) from err
    except didit.APIStatusError as err:
        raise SystemExit(f"API error {err.status} (request {err.request_id})") from err
    except didit.DiditError as err:
        raise SystemExit(str(err)) from err

    print("Session:", session_id, "status:", decision.status)


if __name__ == "__main__":
    main()
