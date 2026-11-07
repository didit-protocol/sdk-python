"""Travel Rule: settings, the VASP directory and your own wallet addresses.

python examples/travel_rule.py
"""

from __future__ import annotations

import didit

client = didit.Didit()

settings = client.travel_rule.retrieve_settings()
print(settings.to_json())

for vasp in client.travel_rule.list_vasps(search="exchange", limit=20):
    print("VASP:", vasp.name)

address = client.travel_rule.wallet_addresses.create(
    address="bc1qexampleexchangewalletaddressxyz", chain="BTC"
)
print("Registered wallet address", address.uuid)

screening = client.wallet_screening.screen(
    wallet_address="bc1qexampleexternalwalletaddressabc", blockchain="BTC"
)
print("Wallet risk:", screening.to_json())
