"""Shared helper types: the NOT_GIVEN sentinel, request option types and file inputs."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import IO, TYPE_CHECKING, Literal, Union

import httpx
from typing_extensions import final, override

__all__ = [
    "NOT_GIVEN",
    "Body",
    "FileContent",
    "FileTypes",
    "Headers",
    "NotGiven",
    "Query",
    "Timeout",
]


@final
class NotGiven:
    """Sentinel for "the caller did not pass this argument".

    It distinguishes an omitted field (left out of the request) from an explicit
    ``None`` (sent as JSON ``null``).
    """

    _instance: NotGiven | None = None

    def __new__(cls) -> NotGiven:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> Literal[False]:
        return False

    @override
    def __repr__(self) -> str:
        return "NOT_GIVEN"

    def __reduce__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()
"""The value of every optional argument that was not passed."""

Timeout = Union[float, httpx.Timeout, None]
Headers = Mapping[str, Union[str, None]]
"""Extra request headers. A ``None`` value removes a header the SDK would send."""
Query = Mapping[str, object]
Body = Mapping[str, object]
"""Extra top-level JSON body fields."""

if TYPE_CHECKING:
    FileContent = Union[IO[bytes], bytes, bytearray, "os.PathLike[str]"]
else:
    FileContent = Union[IO[bytes], bytes, bytearray, os.PathLike]
"""A file: a path, the bytes, or a binary stream."""

FileTypes = Union[
    FileContent,
    tuple[Union[str, None], FileContent],
    tuple[Union[str, None], FileContent, Union[str, None]],
]
"""A file, optionally with a file name and a content type: ``content``,
``(filename, content)`` or ``(filename, content, content_type)``."""
