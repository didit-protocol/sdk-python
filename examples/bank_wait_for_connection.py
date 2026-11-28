"""Wait for a Bank Link connection, then read the accounts.

DIDIT_API_KEY=... python examples/bank_wait_for_connection.py

A sandbox application is enough: Bank data is on for sandbox applications first.
In your own product, send the person to ``link.url`` and wait for the
``bank.connection.created`` webhook instead of polling; the function below shows
both. ``link.url`` and ``link.client_token`` are credentials: hand them to the
person's browser and never write them to a log. The async client has the same
methods; use ``await`` and ``asyncio.sleep``.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Mapping

import didit
from didit import Didit
from didit.types import BankAccount, BankConnection, BankLink


def connection_from_webhook(body: bytes, headers: Mapping[str, str], secret: str) -> str | None:
    """The connection id from a verified ``bank.connection.created`` delivery.

    Always verify before you read the body: ``webhooks.verify`` returns the typed
    event and raises ``WebhookVerificationError`` when the signature is wrong.
    """
    event = didit.webhooks.verify(body, headers, secret)
    if isinstance(event, didit.webhooks.BankConnectionCreatedEvent):
        # bank.connection.created carries its fields next to the envelope, not under ``data``.
        return event.connection_id
    return None


def wait_for_connection(
    client: Didit,
    link_id: str,
    *,
    timeout: float = 900.0,
    interval: float = 3.0,
) -> BankConnection:
    """Poll the link until it completes, then the connection until its first sync is
    readable. Raises ``TimeoutError`` or ``didit.DiditError``.

    Accounts are readable once the first sync ended ``succeeded`` or ``partial`` (the
    connection is then ``active``); ``initial_complete`` is true only for ``succeeded``.
    """
    deadline = time.monotonic() + timeout
    link: BankLink = client.bank.get_link(link_id)
    while link.connection_id is None:
        if link.status in ("cancelled", "expired", "failed"):
            raise RuntimeError(f"link {link.id} ended {link.status}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"link {link.id} is still {link.status}")
        time.sleep(interval)
        link = client.bank.get_link(link_id)

    connection = client.bank.get_connection(link.connection_id)
    while connection.sync is None or connection.sync.initial_status not in ("succeeded", "partial"):
        if connection.status in ("failed", "revoked", "deleted"):
            raise RuntimeError(f"connection {connection.id} is {connection.status}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"connection {connection.id} is still {connection.status}")
        time.sleep(interval)
        connection = client.bank.get_connection(link.connection_id)
    return connection


def main() -> None:
    with Didit() as client:
        # The smallest link: one person, one bank, accounts only, one-time read.
        link = client.bank.create_link(vendor_data="example-user")
        if link.url is None:
            raise SystemExit("the link came back without a url")
        # Hand link.url to the person's browser (a redirect, a button, a QR code).
        # link.url and link.client_token are credentials: never print or log them.
        print("Link created:", link.id, "- send the person to its url and wait for the connection.")

        try:
            connection = wait_for_connection(client, link.id)
        except (TimeoutError, RuntimeError, didit.DiditError) as err:
            raise SystemExit(str(err)) from err

        accounts: list[BankAccount] = list(client.bank.list_accounts(connection.id).items)
        print("Connection:", connection.id, connection.status)
        for account in accounts:
            print(" Account:", account.id, account.name, account.currency)
            balances = client.bank.get_balances(account.id)
            for balance in balances.balances:
                # Amounts are decimal strings, never floats.
                print("  Balance:", balance.type, balance.amount, balance.currency)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit("usage: python examples/bank_wait_for_connection.py")
    main()
