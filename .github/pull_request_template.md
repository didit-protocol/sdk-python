## Summary

<!-- What changes and why. Link the issue or the backend change, if any. -->

## Type of change

<!-- The conventional commit type of the pull request title. It decides the next version. -->

- [ ] `fix`: a bug fix (patch)
- [ ] `feat`: a new capability (minor)
- [ ] `feat!` or `BREAKING CHANGE:`: a breaking change to the public SDK surface (major; minor while 0.x)
- [ ] `docs`, `test`, `refactor`, `perf`, `build`, `ci` or `chore`: no release on its own

## Tests run

<!-- The commands you ran, for example: -->

- [ ] `uv run ruff check .` and `uv run ruff format --check .`
- [ ] `uv run mypy` and `uv run pyright`
- [ ] `uv run python codegen/generate.py --check`
- [ ] `uv run pytest`
- [ ] `uv run pytest -m live` (sandbox, only if relevant)

## Checklist

- [ ] Generated code (`src/didit/types`, `src/didit/resources`, `tests/generated`) was regenerated with `uv run python codegen/generate.py`, not edited by hand.
- [ ] The upstream copies in `openapi/` (`verification.json`, `account.json`, `webhook-vectors.json`) were not edited by hand.
- [ ] Public API changes have tests and a README update.
- [ ] No secrets, API keys or real customer data (fixtures are synthetic).

Parity: same change in the other six SDK repositories, or not applicable because ...
