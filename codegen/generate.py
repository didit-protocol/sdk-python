#!/usr/bin/env python3
"""Regenerate the SDK's generated layer from ``openapi/``.

    uv run python codegen/generate.py           # write src/didit/{types,resources}, tests/generated
    uv run python codegen/generate.py --check   # fail when the committed code is stale
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from didit_codegen.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
