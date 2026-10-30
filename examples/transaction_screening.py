"""Transaction monitoring (KYT): submit a transaction, then walk the latest ones.

python examples/transaction_screening.py
"""

from __future__ import annotations

import didit

client = didit.Didit()

transaction = client.transactions.create(
    transaction_id="your-txn-2026-05-17-001",
    transaction_category="finance",
    transaction_details={
        "direction": "outbound",
        "amount": 1500,
        "currency": "EUR",
        "action_type": "withdrawal",
    },
    subject={"entity_type": "individual", "vendor_data": "user-12345", "full_name": "Maria Garcia"},
)
print("Status:", transaction.status, "score:", transaction.score)

# Newest first; iterating the page fetches the following pages too.
for row in client.transactions.list(limit=50):
    print(row.uuid, row.status)
