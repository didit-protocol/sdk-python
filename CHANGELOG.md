# Changelog

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
