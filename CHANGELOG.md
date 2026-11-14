# Changelog

## [1.19.0](https://github.com/didit-protocol/sdk-python/compare/v1.18.0...v1.19.0) (2026-11-14)


### Features

* **spec:** sync API spec 2026-11-14 ([3a5ad77](https://github.com/didit-protocol/sdk-python/commit/3a5ad77c3574926669ab405e3bb7d2b02536402d))


### Documentation

* add polling and reconciliation examples ([#70](https://github.com/didit-protocol/sdk-python/issues/70)) ([3b6c79a](https://github.com/didit-protocol/sdk-python/commit/3b6c79a7ec57f20ea8e3b2f02acdee57e8df7ede))

## [1.18.0](https://github.com/didit-protocol/sdk-python/compare/v1.17.0...v1.18.0) (2026-11-14)


### Features

* **spec:** sync API spec 2026-11-14 ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))


### API changes that can break typed code

* **spec:** `GET /v3/travel-rule/networks/` response `networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/networks/` response `networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/settings/` response `networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `GET /v3/travel-rule/workspace/` response `settings.networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/billing/` response `settings.networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/claim/` response `settings.networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/confirm/` response `settings.networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `POST /v3/travel-rule/workspace/domain/dns/` response `settings.networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.gtr.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.gtr.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.gtr.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.gtr.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.gtr.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.gtr.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.sygna.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.sygna.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.sygna.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.sygna.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.sygna.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.sygna.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.trust.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.trust.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.trust.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.trust.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.trust.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.trust.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.verifyvasp.connected`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.verifyvasp.platform_available`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.verifyvasp.reason`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.verifyvasp.routed_30d`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.verifyvasp.state`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))
* **spec:** `PUT /v3/travel-rule/settings/` response `networks.verifyvasp.vasps_reachable`: can now be null ([675258d](https://github.com/didit-protocol/sdk-python/commit/675258d98fb5ac398859f239c2804c02dba0340a))

## [1.17.0](https://github.com/didit-protocol/sdk-python/compare/v1.16.0...v1.17.0) (2026-11-13)


### Features

* **spec:** sync API spec 2026-11-13 ([43624f1](https://github.com/didit-protocol/sdk-python/commit/43624f19a355d5f936a12c7150546159d52f5226))

## [1.16.0](https://github.com/didit-protocol/sdk-python/compare/v1.15.0...v1.16.0) (2026-11-13)


### Features

* **spec:** sync API spec 2026-11-13 ([d88361a](https://github.com/didit-protocol/sdk-python/commit/d88361aa32db0280680943c3eb0c1b61e61d3783))

## [1.15.0](https://github.com/didit-protocol/sdk-python/compare/v1.14.1...v1.15.0) (2026-11-12)


### Features

* **spec:** sync API spec 2026-11-12 ([4d3fd44](https://github.com/didit-protocol/sdk-python/commit/4d3fd445dd789d5b24a6954987254014265cec03))


### API changes that can break typed code

* **spec:** `POST /v3/organization/{organization_id}/application/{application_id}/cases/` request body `links[].entity_type`: added (required) ([4d3fd44](https://github.com/didit-protocol/sdk-python/commit/4d3fd445dd789d5b24a6954987254014265cec03))
* **spec:** `POST /v3/organization/{organization_id}/application/{application_id}/cases/` request body `links[].entity_uuid`: added (required) ([4d3fd44](https://github.com/didit-protocol/sdk-python/commit/4d3fd445dd789d5b24a6954987254014265cec03))
* **spec:** `POST /v3/organization/{organization_id}/application/{application_id}/cases/blueprints/{blueprint_uuid}/publish/` response `content_config`: type changed from any to object ([4d3fd44](https://github.com/didit-protocol/sdk-python/commit/4d3fd445dd789d5b24a6954987254014265cec03))

## [1.14.1](https://github.com/didit-protocol/sdk-python/compare/v1.14.0...v1.14.1) (2026-11-12)


### Bug Fixes

* **authentication:** a body nested past the depth limit is not JSON ([77e8fbb](https://github.com/didit-protocol/sdk-python/commit/77e8fbb883f666c727dd1cf5adf49d06057075f5))
* **authentication:** a consent validation error is raised outside the except block, so no parser context ([572a62a](https://github.com/didit-protocol/sdk-python/commit/572a62a3c2ed235834af38f883c02053555d264a))
* **authentication:** a failure to encode a consent request has a fixed message ([dee0b02](https://github.com/didit-protocol/sdk-python/commit/dee0b02bdd3abd76d54fdeef6361f8dead001912))
* **authentication:** a malformed 2xx consent error keeps no parser exception as its cause ([82ec3ee](https://github.com/didit-protocol/sdk-python/commit/82ec3ee437ff05f9d00283917e52799a544ea0e5))
* **authentication:** a malformed 2xx consent message reads the content type from the sanitized response ([97ab037](https://github.com/didit-protocol/sdk-python/commit/97ab037fc4d8684c201711016e96a60d5a6462ff))
* **authentication:** collect consent secrets from the JSON the request carries ([c92755b](https://github.com/didit-protocol/sdk-python/commit/c92755b1cfef53dd5c670e02a093e9bbcc0ae2b9))
* **authentication:** keep the redacted body on the error response ([df2df88](https://github.com/didit-protocol/sdk-python/commit/df2df881dd16a95ab4e907ce34d34d014a9c22aa))
* **authentication:** read consent secrets from the bytes that were sent ([28fc93d](https://github.com/didit-protocol/sdk-python/commit/28fc93de9fcdea23e8413b91bb0b57c7c4152f98))
* **authentication:** redact the parsed agent-consent response structurally ([2c8ccc6](https://github.com/didit-protocol/sdk-python/commit/2c8ccc6819f5f51a05f04534eeb964eea14c28e8))
* **authentication:** redact the parsed agent-consent response, not its raw text ([bead54b](https://github.com/didit-protocol/sdk-python/commit/bead54bd7d61c5f727a5f67243c3f8988b191271))
* **authentication:** sanitize the whole consent response once on receipt ([3de0743](https://github.com/didit-protocol/sdk-python/commit/3de07439ef011443ebb46a09445acdbaa5c0eca7))
* **authentication:** successful consent responses reach the caller unchanged; fold header-name case ([fba4d2c](https://github.com/didit-protocol/sdk-python/commit/fba4d2cf52654bafa8080cdc2c20e2ddb5f1c5c2))
* **authentication:** the debug log of a consent call never records a raw request id ([83279a3](https://github.com/didit-protocol/sdk-python/commit/83279a39b8584a65a06090bc4b5145ccc217e745))
* **authentication:** treat only assertion strings of 16+ characters as secrets ([49554e5](https://github.com/didit-protocol/sdk-python/commit/49554e59c54cfcabdd5358911919825c14a4aa51))
* **authentication:** withhold transport text, redact empty bodies, headers and request id, keep safe key names ([cf51bff](https://github.com/didit-protocol/sdk-python/commit/cf51bff3855c7f9f64e70325ba6a40265448f8cd))


### Documentation

* **authentication:** cite why the secret length minimum is 16 ([02063ff](https://github.com/didit-protocol/sdk-python/commit/02063ffe9b8306cbcd9d73bf76c0f1cc985d6794))

## [1.14.0](https://github.com/didit-protocol/sdk-python/compare/v1.13.0...v1.14.0) (2026-11-11)


### Features

* **spec:** sync API spec 2026-11-11 ([78b9dee](https://github.com/didit-protocol/sdk-python/commit/78b9dee80e49f3828de7e303056481fa73c005ae))

## [1.13.0](https://github.com/didit-protocol/sdk-python/compare/v1.12.0...v1.13.0) (2026-11-11)


### Features

* **spec:** sync API spec 2026-11-11 ([e9b9d77](https://github.com/didit-protocol/sdk-python/commit/e9b9d77c6d52ebd3a3e9fd8f7d0a340bb0e8b85a))

## [1.12.0](https://github.com/didit-protocol/sdk-python/compare/v1.11.0...v1.12.0) (2026-11-11)


### Features

* **spec:** sync API spec 2026-11-11 ([1b78ec9](https://github.com/didit-protocol/sdk-python/commit/1b78ec93d97bdfc80cd674dedd808f56c1148762))
* **spec:** sync API spec 2026-11-11 ([c6b5e05](https://github.com/didit-protocol/sdk-python/commit/c6b5e05bf1ce02ad4cbc04ebbd040c1314c4bfde))
* **spec:** sync API spec 2026-11-11 ([f9f3b7b](https://github.com/didit-protocol/sdk-python/commit/f9f3b7b80d56ed047b8eb5bc4d76bd8167306daf))
* **spec:** sync API spec 2026-11-11 ([8c0f3d6](https://github.com/didit-protocol/sdk-python/commit/8c0f3d6cb5967a8c4110d2daa8d52947872970e5))
* **spec:** sync API spec 2026-11-11 ([6afd5d6](https://github.com/didit-protocol/sdk-python/commit/6afd5d69d337b406ced218d03e9bf2dab34323c8))
* **spec:** sync API spec 2026-11-11 ([f678c74](https://github.com/didit-protocol/sdk-python/commit/f678c7469143aae112f79f3d15f7f8611431289a))
* **spec:** sync API spec 2026-11-11 ([e2a48d6](https://github.com/didit-protocol/sdk-python/commit/e2a48d6331b7f9c9536ada78bbee5984994a57b0))

## [1.11.0](https://github.com/didit-protocol/sdk-python/compare/v1.10.0...v1.11.0) (2026-11-11)


### Features

* **spec:** sync API spec 2026-11-10 ([167f81d](https://github.com/didit-protocol/sdk-python/commit/167f81de1f285ff97a7b063a7d02977864c6f59d))

## [1.10.0](https://github.com/didit-protocol/sdk-python/compare/v1.9.0...v1.10.0) (2026-11-10)


### Features

* **spec:** sync API spec 2026-11-10 ([c5921a2](https://github.com/didit-protocol/sdk-python/commit/c5921a22d28dda375cd1afe2f785871b647cbdf5))

## [1.9.0](https://github.com/didit-protocol/sdk-python/compare/v1.8.0...v1.9.0) (2026-11-10)


### Features

* **spec:** sync API spec 2026-11-10 ([6096396](https://github.com/didit-protocol/sdk-python/commit/60963969c2ad20c34b04b34c065d09638414192f))

## [1.8.0](https://github.com/didit-protocol/sdk-python/compare/v1.7.0...v1.8.0) (2026-11-10)


### Features

* **spec:** sync API spec 2026-11-10 ([9072530](https://github.com/didit-protocol/sdk-python/commit/90725308fc022876610f5e6fac127b600a2b0349))

## [1.7.0](https://github.com/didit-protocol/sdk-python/compare/v1.6.0...v1.7.0) (2026-11-10)


### Features

* **spec:** sync API spec 2026-11-10 ([3ed25f7](https://github.com/didit-protocol/sdk-python/commit/3ed25f732180093447287be5007b33c628671464))

## [1.6.0](https://github.com/didit-protocol/sdk-python/compare/v1.5.0...v1.6.0) (2026-11-10)


### Features

* **spec:** sync API spec 2026-11-10 ([98fcbf0](https://github.com/didit-protocol/sdk-python/commit/98fcbf09fd15d368beb599dde9646d850a552ba9))

## [1.5.0](https://github.com/didit-protocol/sdk-python/compare/v1.4.0...v1.5.0) (2026-11-10)


### Features

* **spec:** sync API spec 2026-11-10 ([887224a](https://github.com/didit-protocol/sdk-python/commit/887224a2d43af4bdd8da15f971e671ed1e327ca7))

## [1.4.0](https://github.com/didit-protocol/sdk-python/compare/v1.3.0...v1.4.0) (2026-11-09)


### Features

* **spec:** sync API spec 2026-11-09 ([02e68b7](https://github.com/didit-protocol/sdk-python/commit/02e68b7f2de08dd562268776e5da31dd519057f6))

## [1.3.0](https://github.com/didit-protocol/sdk-python/compare/v1.2.0...v1.3.0) (2026-11-07)


### Features

* **spec:** sync API spec 2026-11-07 ([f3e55db](https://github.com/didit-protocol/sdk-python/commit/f3e55dbb5bf009106362f4fcd9138210785ee35a))

## [1.2.0](https://github.com/didit-protocol/sdk-python/compare/v1.1.0...v1.2.0) (2026-11-07)


### Features

* **spec:** sync API spec 2026-11-07 ([e579e0b](https://github.com/didit-protocol/sdk-python/commit/e579e0be6b28600e9a3bd556f1edbaf20e255714))

## [1.1.0](https://github.com/didit-protocol/sdk-python/compare/v1.0.2...v1.1.0) (2026-11-05)


### Features

* **spec:** sync API spec 2026-11-05 (application data location) ([7d8d3d0](https://github.com/didit-protocol/sdk-python/commit/7d8d3d0ecb0adcbe865f2bb4cad2a7263b712182))

## [1.0.2](https://github.com/didit-protocol/sdk-python/compare/v1.0.1...v1.0.2) (2026-11-05)


### Bug Fixes

* **codegen:** array file fields in generated tests, lazy session decision in webhook events ([5ebc470](https://github.com/didit-protocol/sdk-python/commit/5ebc4700c6fe58fc1ab3a366cc196d46e237a08d))
* **webhooks:** resolve the session decision lazily at schema build ([151b5e6](https://github.com/didit-protocol/sdk-python/commit/151b5e61138656e6bd0c378ce0d89c4b277a8944))

## [1.0.1](https://github.com/didit-protocol/sdk-python/compare/v1.0.0...v1.0.1) (2026-10-29)


### Miscellaneous Chores

* release 1.0.1 ([6922b70](https://github.com/didit-protocol/sdk-python/commit/6922b7080f345870855483e367a60ec514957cff))

## [1.0.0](https://github.com/didit-protocol/sdk-python/compare/v0.1.0...v1.0.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **spec:** the API spec sync changes the SDK surface (nullable fields, removed fields, account.organizations.list returns a page, the session decision response is the SessionDecision component).

### Features

* add bank.account_check (POST /v3/bank/account-check/) and bank_verifications on the decision ([5a66ae8](https://github.com/didit-protocol/sdk-python/commit/5a66ae86ba4fa01dfab37dbe8b7427897e21d969))
* **spec:** sync API spec 2026-10-23 ([#3](https://github.com/didit-protocol/sdk-python/issues/3)) ([9003159](https://github.com/didit-protocol/sdk-python/commit/90031599f86279be5d19e977acc0ff023b9f9f92))
* **spec:** sync API spec 2026-10-27 ([#9](https://github.com/didit-protocol/sdk-python/issues/9)) ([f17911b](https://github.com/didit-protocol/sdk-python/commit/f17911bd1146cae17ac8a2d638bf39ca5f364c35))


### Miscellaneous Chores

* release 1.0.0 ([b1cd3b0](https://github.com/didit-protocol/sdk-python/commit/b1cd3b0c3465a995b4ad3d36c2ac390f2a03a725))
