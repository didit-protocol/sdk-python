"""The shared breaking-change vectors, ``openapi/breaking-vectors.json`` (DESIGN.md 3.1).

The other six server SDKs copy the file byte for byte and run every case through their own
detector. Here every case runs through ``spec_sync``, and the file must be exactly what
``codegen/breaking_vectors.py`` writes.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any

import pytest

CODEGEN = pathlib.Path(__file__).resolve().parents[1]
REPO = CODEGEN.parent
VECTORS_PATH = REPO / "openapi" / "breaking-vectors.json"
sys.path.insert(0, str(CODEGEN))

import breaking_vectors  # noqa: E402
import spec_sync  # noqa: E402

VECTORS: Any = json.loads(VECTORS_PATH.read_text("utf-8"))
CASES: list[Any] = VECTORS["cases"]
BY_NAME = {case["name"]: case for case in CASES}


def test_the_file_names_its_rules_and_its_generator() -> None:
    assert list(VECTORS) == ["version", "rules", "generator", "cases"]
    assert VECTORS["version"] == 1
    assert VECTORS["rules"] == "docs/DESIGN.md section 3.1"
    assert VECTORS["generator"] == "codegen/breaking_vectors.py"
    assert (REPO / VECTORS["generator"]).is_file()


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_every_case_passes(case: Any) -> None:
    assert list(case) == ["name", "rule", "before", "after", "expect"]
    expect = case["expect"]
    assert spec_sync.classify(case["before"], case["after"]) == (
        expect["type"],
        expect["breaking"],
    )


def test_the_file_is_what_the_generator_writes_every_time() -> None:
    first, second = breaking_vectors.render(), breaking_vectors.render()
    assert first == second
    assert VECTORS_PATH.read_bytes() == first.encode()
    assert breaking_vectors.main(["--check"]) == 0


def test_every_rule_is_a_design_bullet_with_at_least_two_cases() -> None:
    design = (REPO / "docs" / "DESIGN.md").read_text("utf-8")
    section = design.split("### 3.1 Spec sync", 1)[1].split("\n## ", 1)[0]
    for rule, opening in breaking_vectors.RULES.items():
        assert f"\n{opening}" in section, rule
        assert sum(case["rule"] == rule for case in CASES) >= 2, rule
    assert {case["rule"] for case in CASES} == set(breaking_vectors.RULES)


def test_names_are_unique_and_every_line_is_normalized_and_sorted() -> None:
    assert len(BY_NAME) == len(CASES)
    for case in CASES:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case["name"]), case["name"]
        expect = case["expect"]
        assert expect["type"] in ("feat(spec)", "chore(spec)")
        assert expect["breaking"] == sorted(set(expect["breaking"])), case["name"]
        for line in expect["breaking"]:
            assert line.isascii(), line
            assert breaking_vectors.BREAKING.fullmatch(line), line


def _counted(side: str) -> set[str]:
    """The kinds counted somewhere in the file on one side: "response", "request" (the body
    and the parameters) or "operation"."""
    found: set[str] = set()
    for case in CASES:
        for line in case["expect"]["breaking"]:
            target, kind = line.split(": ", 1)
            where = target.split(" ", 2)[2] if target.count(" ") >= 2 else "operation"
            if where.startswith("response"):
                where = "response"
            elif where != "operation":
                where = "request"
            if where == side:
                found.add(re.sub(r"^(type|enum value) .*", r"\1", kind))
    return found


def test_each_counted_kind_is_covered_in_responses_and_in_requests() -> None:
    assert _counted("response") == {
        "removed",
        "type",
        "can now be null",
        "no longer required",
        "enum value",
    }
    assert _counted("request") == {"removed", "type", "now required", "enum value"}
    assert _counted("operation") == {"body now required", "operation removed"}


# The issue's coverage list: every item names the cases that cover it.
COVERAGE = {
    "listed, not counted": [
        "response-field-added-is-listed",
        "response-enum-value-added-is-listed",
        "parameter-can-now-be-null-is-listed",
        "body-field-can-now-be-null-is-listed",
        "parameter-no-longer-required-is-listed",
        "body-field-no-longer-required-is-listed",
        "operation-added-is-listed",
        "union-variant-title-renamed-is-listed",
        "added-status-with-another-body-is-listed",
    ],
    "documentation only": ["response-documentation-only", "request-documentation-only"],
    "$ref": ["response-ref-and-array-items", "request-body-ref-field-removed"],
    "array items": ["response-ref-and-array-items", "request-body-array-item-enum-value-removed"],
    "allOf": ["response-all-of"],
    "union with an added variant": ["union-variant-added-and-paired-variant-changed"],
    "union with a reordered variant": ["union-variants-reordered-and-paired-variant-changed"],
    "server: false": [
        "server-false-operation-removed-is-listed",
        "server-false-operation-changes-are-listed",
    ],
    "moved operation": ["moved-operation-changes-count-under-its-new-path"],
}


@pytest.mark.parametrize("item", COVERAGE)
def test_the_file_covers(item: str) -> None:
    for name in COVERAGE[item]:
        case = BY_NAME[name]
        documents = json.dumps([case["before"], case["after"]])
        breaking = case["expect"]["breaking"]
        if item == "listed, not counted":
            assert (case["expect"]["type"], breaking) == ("feat(spec)", []), name
        elif item == "documentation only":
            assert (case["expect"]["type"], breaking) == ("chore(spec)", []), name
        elif item == "$ref":
            assert '"$ref"' in documents and breaking, name
        elif item == "array items":
            assert any("[]" in line for line in breaking), name
        elif item == "allOf":
            assert '"allOf"' in documents and breaking, name
        elif item.startswith("union"):
            assert any("(oneOf " in line for line in breaking), name
        elif item == "server: false":
            assert '"server": false' in documents and not breaking, name
        else:
            assert set(case["before"]["paths"]).isdisjoint(case["after"]["paths"]) and breaking


def test_the_real_api_change_of_2026_11_04_gives_the_same_list_in_vector_form(
    tmp_path: pathlib.Path,
) -> None:
    # The first-round fixtures, normalized the way the vectors spell them.
    fixtures = CODEGEN / "tests" / "fixtures"
    before = json.loads((fixtures / "verification-9fe57fc69299601e59cc7a64c1db370fea5c7461.json").read_bytes())  # fmt: skip
    after = json.loads((fixtures / "verification-e002a815773bbd1599256e2774046ee76520c6c8.json").read_bytes())  # fmt: skip
    commit_type, breaking = spec_sync.classify(before, after)
    assert commit_type == "feat(spec)"
    assert len(breaking) == 14
    assert "POST /v3/email/risk/ response email.enrichment.reason_codes[]: type string -> object" in breaking  # fmt: skip
    assert "POST /v3/kyb/ubo/ response kyb_registry.registry_data: can now be null" in breaking
