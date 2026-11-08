"""Debug logging (docs/DESIGN.md section 6).

The SDK logs to the ``didit`` logger at debug level: method, path, status,
duration and request id, never bodies or headers. ``DIDIT_LOG=debug`` also
prints those lines to stderr without any logging setup in your app.
"""

from __future__ import annotations

import logging
import os

__all__ = ["setup_logging"]

logger = logging.getLogger("didit")


def setup_logging() -> None:
    level = (os.environ.get("DIDIT_LOG") or "").strip().lower()
    if level != "debug":
        return
    if not any(getattr(h, "_didit", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(asctime)s %(name)s %(levelname)s] %(message)s"))
        handler._didit = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
