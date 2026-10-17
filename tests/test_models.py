"""Response models: unknown fields kept, contract mismatches tolerated, absent versus null (DESIGN 5.1)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pydantic

import didit
from didit._models import BaseModel, construct_type, validate_response
from didit.types import SessionsCreateResponse, TransactionDetail
from tests.mock_api import SESSION, MockAPI


class Inner(BaseModel):
    name: str
    when: dt.datetime | None = None


class Outer(BaseModel):
    id: int
    inner: Inner | None = None
    items: list[Inner] | None = None
    tags: dict[str, Inner] | None = None
    either: Inner | int | None = None


def test_unknown_fields_are_kept() -> None:
    api = MockAPI().json(201, {**SESSION, "brand_new_field": {"x": 1}})
    session = api.client().sessions.create(workflow_id="w")
    assert isinstance(session, SessionsCreateResponse)
    assert session.model_extra == {"brand_new_field": {"x": 1}}
    assert session.to_dict()["brand_new_field"] == {"x": 1}
    assert '"brand_new_field"' in session.to_json()


def test_absent_and_null_are_distinguishable() -> None:
    model = validate_response(Outer, {"id": 1, "inner": None})
    assert model.inner is None
    assert model.items is None
    assert "inner" in model.model_fields_set
    assert "items" not in model.model_fields_set
    assert model.to_dict() == {"id": 1, "inner": None}


def test_dates_are_parsed() -> None:
    model = validate_response(Outer, {"id": 1, "inner": {"name": "a", "when": "2026-01-02T03:04:05Z"}})
    assert model.inner.when == dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)


def test_contract_mismatch_never_raises() -> None:
    data: dict[str, Any] = {
        "id": "not-an-int",
        "inner": {"name": 5, "when": "yesterday"},
        "items": [{"name": "ok"}, {"bad": True}, "junk"],
        "tags": {"a": {"name": "x"}},
        "either": {"name": "n"},
        "extra": 1,
    }
    model = validate_response(Outer, data)
    assert isinstance(model, Outer)
    loose: Any = model
    assert loose.id == "not-an-int"
    assert isinstance(model.inner, Inner)
    assert loose.inner.name == 5
    assert loose.inner.when == "yesterday"
    assert model.items is not None
    assert isinstance(model.items[0], Inner)
    assert loose.items[2] == "junk"
    assert model.tags is not None
    assert isinstance(model.tags["a"], Inner)
    assert isinstance(model.either, Inner)
    assert model.model_extra == {"extra": 1}


def test_construct_type_edge_cases() -> None:
    assert construct_type(int, None) is None
    assert construct_type(Inner, "not a dict") == "not a dict"
    assert construct_type(list[int], "x") == "x"
    assert construct_type(dict[str, int], 3) == 3
    assert construct_type(dt.date, "2026-01-01") == dt.date(2026, 1, 1)
    assert construct_type(dt.date, "bad") == "bad"
    assert construct_type(Inner | int, "str") == "str"
    assert construct_type(object, {"a": 1}) == {"a": 1}


def test_real_model_with_wrong_shape() -> None:
    api = MockAPI().json(200, {"uuid": 1234, "status": {"weird": True}, "surprise": [1]})
    transaction = api.client().transactions.retrieve("t-1")
    assert isinstance(transaction, TransactionDetail)
    loose: Any = transaction
    assert loose.uuid == 1234
    assert loose.status == {"weird": True}
    assert transaction.model_extra == {"surprise": [1]}


def test_validate_response_passthrough() -> None:
    assert validate_response(object, {"a": 1}) == {"a": 1}
    assert validate_response(list[int], ["1", 2]) == [1, 2]
    assert validate_response(list[int], ["x"]) == ["x"]


def test_public_base_model() -> None:
    assert issubclass(SessionsCreateResponse, didit.BaseModel)
    assert issubclass(didit.BaseModel, pydantic.BaseModel)
