"""Every generated type imports and builds (models are built lazily, so check them all)."""

from __future__ import annotations

import importlib
import pkgutil
import subprocess
import sys

import pydantic
import pytest

import didit
import didit.resources
import didit.types


def test_every_exported_type_resolves_and_builds() -> None:
    assert len(didit.types.__all__) > 800
    models = 0
    for name in didit.types.__all__:
        value = getattr(didit.types, name)
        if isinstance(value, type) and issubclass(value, pydantic.BaseModel):
            # Response models: building the schema resolves every annotation.
            value.model_rebuild(force=True)
            pydantic.TypeAdapter(value).json_schema()
            models += 1
        else:
            # Request TypedDicts and aliases only need to be importable.
            assert value is not None
    assert models > 500
    assert "SessionsCreateResponse" in dir(didit.types)
    with pytest.raises(AttributeError):
        getattr(didit.types, "NoSuchType")  # noqa: B009


def test_every_generated_module_imports() -> None:
    for package in (didit.types, didit.resources):
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            importlib.import_module(info.name)


def test_import_is_light() -> None:
    code = (
        "import sys, didit; "
        "loaded = [m for m in sys.modules if m.startswith(('didit.resources.', 'didit.types.'))]; "
        "print(len(loaded), 'cryptography' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.split()
    # Only the decision model the webhook events reuse is loaded up front.
    assert int(out[0]) < 10
    assert out[1] == "False"
