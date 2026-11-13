"""Poll a Didit session decision until it is final.

pip install didit-sdk
DIDIT_API_KEY=... python examples/poll_decision.py <session_id>
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable

import didit
from didit.types import SessionDecision

TERMINAL_STATUSES = frozenset({"Approved", "Declined", "Expired", "Abandoned"})


def poll_decision(
    client: didit.Didit,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--stop-on-review", action="store_true")
    args = parser.parse_args()

    with didit.Didit() as client:
        try:
            decision = poll_decision(
                client,
                args.session_id,
                timeout=args.timeout,
                stop_on_review=args.stop_on_review,
            )
        except TimeoutError as err:
            raise SystemExit(str(err)) from err

    print(args.session_id, decision.status)


if __name__ == "__main__":
    main()
