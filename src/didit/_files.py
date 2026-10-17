"""File inputs for multipart uploads (docs/DESIGN.md section 8)."""

from __future__ import annotations

import io
import mimetypes
import os
import pathlib
from typing import Any, Union, cast

from ._types import FileContent, FileTypes

__all__ = ["is_file_input", "to_httpx_file"]

HttpxFile = tuple[Union[str, None], bytes, Union[str, None]]


def is_file_input(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, os.PathLike, io.IOBase)):
        return True
    if isinstance(value, tuple) and len(value) in (2, 3):  # pyright: ignore[reportUnknownArgumentType]
        return is_file_input(value[1])
    return hasattr(value, "read")


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
        data = bytes(cast("bytes", raw))
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
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return filename, data, content_type
