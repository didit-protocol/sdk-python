"""AML screening of a person (sanctions, PEP, adverse media).

python examples/aml_screening.py "Maria Garcia"
"""

from __future__ import annotations

import sys

import didit

client = didit.Didit()

try:
    result = client.aml.screen(
        full_name=sys.argv[1] if len(sys.argv) > 1 else "Maria Garcia",
        date_of_birth="1992-03-14",
        nationality="ESP",
        vendor_data="user-123",
        idempotency_key="aml-user-123-2026-10-17",  # a retry with the same key is not billed twice
    )
except didit.RateLimitError as err:
    print("Slow down; request id", err.request_id)
    raise
print(result.to_json())
