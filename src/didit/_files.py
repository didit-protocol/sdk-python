"""File inputs for multipart uploads (docs/DESIGN.md section 8)."""

from __future__ import annotations

import mimetypes
import os
import pathlib
from typing import Any, Union, cast

from ._types import FileContent, FileTypes

__all__ = ["guess_content_type", "to_httpx_file"]

HttpxFile = tuple[Union[str, None], bytes, Union[str, None]]

# The upload types the API accepts. ``mimetypes`` alone depends on the host (the
# Windows registry, /etc/mime.types), so these never vary between machines.
_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".csv": "text/csv",
    ".ndjson": "application/x-ndjson",
    ".json": "application/json",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


def guess_content_type(filename: str) -> str:
    """The content type for ``filename``, the same on every operating system for
    the types the API accepts."""
    known = _CONTENT_TYPES.get(os.path.splitext(filename)[1].lower())
    if known is not None:
        return known
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def to_httpx_file(value: FileTypes) -> HttpxFile:
    """Read a file input into ``(filename, content, content_type)``.

    The content is read once into memory so that a retried request sends the
    same bytes again.
    """
    filename: str | None = None
    content_type: str | None = None
    content: FileContent
    if isinstance(value, tuple):
        parts = cast("tuple[Any, ...]", value)
        if len(parts) == 2:
            filename, content = parts
        elif len(parts) == 3:
            filename, content, content_type = parts
        else:
            raise TypeError(
                "A file tuple is (filename, content) or (filename, content, content_type)."
            )
    else:
        content = value
    data: bytes
    if isinstance(content, (bytes, bytearray)):
        data = bytes(content)
    elif isinstance(content, os.PathLike):
        path = pathlib.Path(content)
        data = path.read_bytes()
        if filename is None:
            filename = path.name
    elif hasattr(content, "read"):
        raw: object = content.read()
        if isinstance(raw, str):
            raise TypeError("Open files in binary mode ('rb') before uploading them.")
        data = bytes(cast("bytes | bytearray", raw))
        if filename is None:
            name = getattr(content, "name", None)
            if isinstance(name, str):
                filename = os.path.basename(name)
    else:
        raise TypeError(
            f"Expected a path, bytes or a binary stream for a file, got {type(content).__name__}."
        )
    if filename is None:
        filename = "upload"
    if content_type is None:
        content_type = guess_content_type(filename)
    return filename, data, content_type
