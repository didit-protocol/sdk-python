"""Transaction monitoring (KYT): submit a transaction, then list the ones that need review.

    python examples/transaction_screening.py
"""

from __future__ import annotations

import didit

client = didit.Didit()

transaction = client.transactions.create(
    transaction_id="your-txn-2026-05-17-001",
    transaction_category="finance",
    transaction_details={"direction": "outbound", "amount": 1500, "currency": "EUR", "action_type": "withdrawal"},
    subject={"entity_type": "individual", "vendor_data": "user-12345", "full_name": "Maria Garcia"},
    idempotency_key="your-txn-2026-05-17-001",
)
print("Status:", transaction.status, "score:", transaction.score)

for row in client.transactions.list(status="IN_REVIEW", limit=50):
    print(row.uuid, row.status)
