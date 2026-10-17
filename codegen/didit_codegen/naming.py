"""Name conversions for the generated code (docs/DESIGN.md sections 4 and 5.1)."""

from __future__ import annotations

import keyword
import re

_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z0-9])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")

# Names the generated method signatures use for per-request options.
RESERVED_KWARGS = frozenset(
    {"self", "extra_headers", "extra_query", "extra_body", "timeout", "idempotency_key"}
)


def words(text: str) -> list[str]:
    return _WORD.findall(re.sub(r"[^A-Za-z0-9]+", " ", text))


def _cap(word: str) -> str:
    if word.isupper() and len(word) > 1:
        return word[0] + word[1:].lower()
    return word[:1].upper() + word[1:]


def pascal(text: str) -> str:
    """``key_people_checks`` -> ``KeyPeopleChecks``; ``ID verification`` -> ``IdVerification``."""
    out = "".join(_cap(w) for w in words(text))
    if not out:
        return "Value"
    if out[0].isdigit():
        out = "V" + out
    return out


def snake(text: str) -> str:
    """``sessionId`` -> ``session_id``; ``Idempotency-Key`` -> ``idempotency_key``."""
    out = "_".join(w.lower() for w in words(text))
    if not out:
        return "value"
    if out[0].isdigit():
        out = "v_" + out
    return out


def identifier(name: str, *, taken: frozenset[str] = frozenset()) -> str:
    """A valid, non-keyword Python identifier for ``name``; ``from`` -> ``from_``."""
    out = name if name.isidentifier() else snake(name)
    if out.startswith("_"):
        out = out.lstrip("_") or "value"
        if not out.isidentifier():
            out = "v_" + out
    while keyword.iskeyword(out) or out in taken:
        out += "_"
    return out


def resource_class(resource: str) -> str:
    """``sessions.imports`` -> ``SessionsImports``."""
    return "".join(pascal(segment) for segment in resource.split("."))
