# Changelog

## [1.0.0](https://github.com/didit-protocol/sdk-python/compare/v0.1.0...v1.0.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **spec:** the API spec sync changes the SDK surface (nullable fields, removed fields, account.organizations.list returns a page, the session decision response is the SessionDecision component).

### Features

* add bank.account_check (POST /v3/bank/account-check/) and bank_verifications on the decision ([5a66ae8](https://github.com/didit-protocol/sdk-python/commit/5a66ae86ba4fa01dfab37dbe8b7427897e21d969))
* **spec:** sync API spec 2026-10-23 ([#3](https://github.com/didit-protocol/sdk-python/issues/3)) ([9003159](https://github.com/didit-protocol/sdk-python/commit/90031599f86279be5d19e977acc0ff023b9f9f92))
* **spec:** sync API spec 2026-10-27 ([#9](https://github.com/didit-protocol/sdk-python/issues/9)) ([f17911b](https://github.com/didit-protocol/sdk-python/commit/f17911bd1146cae17ac8a2d638bf39ca5f364c35))


### Miscellaneous Chores

* release 1.0.0 ([b1cd3b0](https://github.com/didit-protocol/sdk-python/commit/b1cd3b0c3465a995b4ad3d36c2ac390f2a03a725))
