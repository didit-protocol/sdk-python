"""Standalone ID verification: upload the two sides of a document.

    python examples/id_verification.py front.jpg back.jpg
"""

from __future__ import annotations

import pathlib
import sys

import didit

client = didit.Didit()

front, back = (pathlib.Path(p) for p in sys.argv[1:3])
result = client.id_verification.verify(
    front_image=front,  # a path, bytes, an open binary file, or (filename, content, content_type)
    back_image=back,
    vendor_data="user-123",
)
print(result.to_json())
