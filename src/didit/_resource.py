"""Base classes of the generated resources."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient

__all__ = ["AsyncAPIResource", "SyncAPIResource"]


class SyncAPIResource:
    _client: SyncAPIClient

    def __init__(self, client: SyncAPIClient) -> None:
        self._client = client


class AsyncAPIResource:
    _client: AsyncAPIClient

    def __init__(self, client: AsyncAPIClient) -> None:
        self._client = client
