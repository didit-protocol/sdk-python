#!/usr/bin/env python3
"""Sync ``openapi/`` with the published API contract (docs/DESIGN.md section 3.1).

    uv run python codegen/spec_sync.py --summary spec-sync-summary.md

Downloads https://docs.didit.me/openapi-25.json and openapi-auth.json, and when
either changed:

- checks that each download is an OpenAPI 3 document with paths, and writes
  nothing otherwise;
- writes them byte for byte to ``openapi/verification.json`` / ``account.json``
  and records URL, SHA-256 and fetch time in ``openapi/SOURCE.json``;
- drops ``overlay.json`` entries that upstream now carries as ``x-didit-sdk``;
- never deletes a public method silently: a server method whose operation was
  removed, or whose naming changed upstream (a rename), is recorded, fully
  dereferenced, in ``openapi/deprecated-operations.json``, so the SDK keeps it
  as a deprecated method until the next minor version (``remove_in``). An
  operation whose SDK name reappears on another path counts as moved, not removed;
- writes a Markdown summary of added, removed, renamed and changed operations
  and schemas. Changes are compared field by field, nested objects, arrays,
  types, enums, nullability and required fields included, and every change
  that can break code written against the SDK is listed under "Breaking changes".

It prints ``changed=true|false`` to ``$GITHUB_OUTPUT`` when that is set. The
generator, not this script, regenerates the code.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.request
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
UPSTREAM = {
    "verification.json": "https://docs.didit.me/openapi-25.json",
    "account.json": "https://docs.didit.me/openapi-auth.json",
}
PREFIXES = {"verification.json": "", "account.json": "account "}
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
# Keys that document a schema without changing what is sent or received.
DOC_KEYS = frozenset({"description", "summary", "title", "example", "examples", "externalDocs"})
MAX_NOTES = 25
Json = Any


class SpecSyncError(Exception):
    """A download is not a document the SDK can be generated from."""


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "didit-sdk-python spec-sync"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URLs
        data: bytes = response.read()
    return data


def check_openapi(name: str, data: bytes) -> Json:
    """Parse ``data`` and refuse anything that is not an OpenAPI 3 document with paths
    (an error page or a maintenance JSON must never replace the contract)."""
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise SpecSyncError(f"{name}: the download is not JSON ({exc}).") from exc
    if not isinstance(doc, dict):
        raise SpecSyncError(f"{name}: the download is not a JSON object.")
    version = doc.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise SpecSyncError(
            f"{name}: the download is not an OpenAPI 3 document (openapi={version!r})."
        )
    paths = doc.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise SpecSyncError(f"{name}: the download has no paths.")
    return doc


def _pointer(doc: Json, ref: str) -> Json:
    cur = doc
    for part in ref[2:].split("/"):
        cur = cur[part.replace("~1", "/").replace("~0", "~")]
    return cur


def dereference(doc: Json, node: Json, depth: int = 0) -> Json:
    """``node`` with every local ``$ref`` inlined (self-contained for deprecated operations)."""
    if depth > 64:
        return {}
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            try:
                found = _pointer(doc, node["$ref"])
            except (KeyError, IndexError, TypeError):
                # A dangling reference upstream: keep it visible; the generator reports it.
                return {"x-unresolved-ref": node["$ref"]}
            target = dereference(doc, found, depth + 1)
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return {**target, **extra} if isinstance(target, dict) else target
        return {k: dereference(doc, v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [dereference(doc, v, depth + 1) for v in node]
    return node


def operations(doc: Json, prefix: str) -> dict[str, Json]:
    out: dict[str, Json] = {}
    for path, item in doc.get("paths", {}).items():
        for method in METHODS:
            if method in item:
                op = dict(item[method])
                if item.get("parameters"):
                    op["parameters"] = [*item["parameters"], *op.get("parameters", [])]
                out[f"{prefix}{method.upper()} {path}"] = op
    return out


# Schema comparison ----------------------------------------------------------------------


def _shape(node: Json) -> Json:
    """``node`` without documentation, so that only what is sent or received compares."""
    if isinstance(node, dict):
        return {
            k: _shape(v)
            for k, v in node.items()
            if k not in DOC_KEYS and not str(k).startswith("x-")
        }
    if isinstance(node, list):
        return [_shape(v) for v in node]
    return node


def _types(schema: Json) -> set[str]:
    raw = schema.get("type")
    types = set(raw) if isinstance(raw, list) else ({raw} if isinstance(raw, str) else set())
    if schema.get("nullable") is True:
        types.add("null")
    for variant in schema.get("anyOf", []) + schema.get("oneOf", []):
        if isinstance(variant, dict) and variant.get("type") == "null":
            types.add("null")
    return types


def _object_props(schema: Json) -> tuple[dict[str, Json], set[str]]:
    props: dict[str, Json] = {}
    required: set[str] = set()
    stack = [schema]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        props.update(cur.get("properties") or {})
        required |= set(cur.get("required") or [])
        stack.extend(cur.get("allOf") or [])
    return props, required


def _variants(schema: Json, keyword: str) -> list[Json]:
    return [
        v
        for v in schema.get(keyword) or []
        if not (isinstance(v, dict) and v.get("type") == "null")
    ]


def diff_schema(
    old: Json,
    new: Json,
    where: str,
    *,
    request: bool,
    notes: list[tuple[str, bool]],
    depth: int = 0,
) -> None:
    """Append ``(note, breaking)`` for every difference between two dereferenced schemas.

    ``request`` tells which side the schema is on: removing an enum value breaks
    callers that send it, while a response enum is open (DESIGN 5.1) and gaining
    or losing a value breaks nobody; a field that becomes required breaks callers,
    a response field that is no longer always present breaks readers.
    """
    if depth > 16 or _shape(old) == _shape(new):
        return
    if not isinstance(old, dict) or not isinstance(new, dict):
        notes.append((f"{where}: schema replaced", True))
        return
    old_types, new_types = _types(old), _types(new)
    old_plain, new_plain = old_types - {"null"}, new_types - {"null"}
    if old_plain and new_plain and old_plain != new_plain:
        widened = old_plain == {"integer"} and new_plain == {"number"}
        narrowed = old_plain == {"number"} and new_plain == {"integer"}
        harmless = (request and widened) or (not request and narrowed)
        notes.append(
            (
                f"{where}: type {'/'.join(sorted(old_plain))} -> {'/'.join(sorted(new_plain))}",
                not harmless,
            )
        )
        return
    if "null" in new_types and "null" not in old_types and not request:
        notes.append((f"{where}: can now be null", True))
    if "null" in old_types and "null" not in new_types and request:
        notes.append((f"{where}: no longer accepts null", True))

    old_enum, new_enum = old.get("enum"), new.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list):
        gone = [v for v in old_enum if v not in new_enum]
        added = [v for v in new_enum if v not in old_enum]
        if gone:
            notes.append((f"{where}: values removed {json.dumps(gone)}", request))
        if added:
            notes.append((f"{where}: values added {json.dumps(added)}", False))
    elif isinstance(new_enum, list) and not isinstance(old_enum, list):
        notes.append((f"{where}: now limited to {json.dumps(new_enum)}", request))
    elif isinstance(old_enum, list):
        notes.append((f"{where}: no longer limited to fixed values", False))

    old_props, old_req = _object_props(old)
    new_props, new_req = _object_props(new)
    for name in sorted(set(old_props) - set(new_props)):
        notes.append((f"{where}.{name}: removed", True))
    for name in sorted(set(new_props) - set(old_props)):
        required = request and name in new_req
        notes.append((f"{where}.{name}: added{' (required)' if required else ''}", required))
    for name in sorted(set(old_props) & set(new_props)):
        if request and name in new_req and name not in old_req:
            notes.append((f"{where}.{name}: now required", True))
        if not request and name in old_req and name not in new_req:
            notes.append((f"{where}.{name}: no longer always present", True))
        diff_schema(
            old_props[name], new_props[name], f"{where}.{name}",
            request=request, notes=notes, depth=depth + 1,
        )  # fmt: skip
    for key, suffix in (("items", "[]"), ("additionalProperties", "{}")):
        if isinstance(old.get(key), dict) or isinstance(new.get(key), dict):
            diff_schema(
                old.get(key) or {}, new.get(key) or {}, f"{where}{suffix}",
                request=request, notes=notes, depth=depth + 1,
            )  # fmt: skip
    for keyword in ("oneOf", "anyOf"):
        old_vars, new_vars = _variants(old, keyword), _variants(new, keyword)
        if len(new_vars) < len(old_vars):
            notes.append(
                (f"{where}: {len(old_vars) - len(new_vars)} {keyword} variant(s) removed", True)
            )
        elif len(new_vars) > len(old_vars):
            notes.append(
                (f"{where}: {len(new_vars) - len(old_vars)} {keyword} variant(s) added", False)
            )
        else:
            for index, (a, b) in enumerate(zip(old_vars, new_vars, strict=True)):
                diff_schema(
                    a, b, f"{where}<{keyword} {index + 1}>",
                    request=request, notes=notes, depth=depth + 1,
                )  # fmt: skip


def _body(op: Json) -> tuple[set[str], Json]:
    content = (op.get("requestBody") or {}).get("content") or {}
    media = content.get("application/json") or content.get("multipart/form-data") or {}
    return set(content), media.get("schema", {})


def _success(op: Json) -> tuple[set[str], Json]:
    for code, response in sorted((op.get("responses") or {}).items()):
        if str(code).startswith("2"):
            content = response.get("content") or {}
            return set(content), (content.get("application/json") or {}).get("schema", {})
    return set(), {}


def describe_change(old_doc: Json, old: Json, new_doc: Json, new: Json) -> tuple[list[str], bool]:
    """Human-readable differences of one operation, and whether any is breaking."""
    found: list[tuple[str, bool]] = []
    old_params = {
        (p.get("in"), p.get("name")): p for p in dereference(old_doc, old.get("parameters", []))
    }
    new_params = {
        (p.get("in"), p.get("name")): p for p in dereference(new_doc, new.get("parameters", []))
    }
    for key in sorted(set(old_params) - set(new_params), key=str):
        found.append((f"parameter removed: {key[1]} ({key[0]})", True))
    for key in sorted(set(new_params) - set(old_params), key=str):
        required = bool(new_params[key].get("required"))
        found.append(
            (f"parameter added: {key[1]} ({key[0]}{', required' if required else ''})", required)
        )
    for key in sorted(set(old_params) & set(new_params), key=str):
        if not old_params[key].get("required") and new_params[key].get("required"):
            found.append((f"parameter now required: {key[1]}", True))
        diff_schema(
            old_params[key].get("schema") or {}, new_params[key].get("schema") or {},
            f"parameter {key[1]}", request=True, notes=found,
        )  # fmt: skip

    old_types, old_body = _body(old)
    new_types, new_body = _body(new)
    if old_types != new_types and old_types and new_types:
        found.append(
            (
                f"request content type {sorted(old_types)} -> {sorted(new_types)}",
                not old_types <= new_types,
            )
        )
    if (old.get("requestBody") or {}).get("required") is not True and (
        new.get("requestBody") or {}
    ).get("required") is True:
        found.append(("request body now required", True))
    diff_schema(
        dereference(old_doc, old_body), dereference(new_doc, new_body), "body",
        request=True, notes=found,
    )  # fmt: skip

    old_types, old_resp = _success(old)
    new_types, new_resp = _success(new)
    if old_types != new_types:
        found.append((f"response content type {sorted(old_types)} -> {sorted(new_types)}", True))
    diff_schema(
        dereference(old_doc, old_resp), dereference(new_doc, new_resp), "response",
        request=False, notes=found,
    )  # fmt: skip

    if old.get("deprecated") is not True and new.get("deprecated") is True:
        found.append(("marked deprecated upstream", False))
    if old.get("x-didit-sdk") != new.get("x-didit-sdk") and new.get("x-didit-sdk") is not None:
        found.append((f"x-didit-sdk now {json.dumps(new['x-didit-sdk'], sort_keys=True)}", False))
    if not found:
        return ["descriptions, examples or other details changed"], False
    breaking = any(b for _, b in found)
    # Breaking notes first, then the rest, capped so that one huge change stays readable.
    ordered = [n for n, b in found if b] + [n for n, b in found if not b]
    notes = [f"{n} (breaking)" if (n, True) in found else n for n in ordered]
    if len(notes) > MAX_NOTES:
        notes = [*notes[:MAX_NOTES], f"and {len(notes) - MAX_NOTES} more differences"]
    return notes, breaking


# Versions -------------------------------------------------------------------------------


def _version() -> str:
    text = (REPO / "src" / "didit" / "_version.py").read_text("utf-8")
    match = re.search(r'__version__ = "([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def next_minor(version: str) -> str:
    """The version in which a method deprecated in ``version`` is deleted."""
    match = re.match(r"(\d+)\.(\d+)", version)
    if not match:
        return "0.1.0"
    return f"{match.group(1)}.{int(match.group(2)) + 1}.0"


# The sync -------------------------------------------------------------------------------


def _name(naming: Json) -> str:
    return f"{naming['resource']}.{naming['method']}"


def sync(
    openapi_dir: pathlib.Path,
    downloads: dict[str, bytes],
    *,
    today: dt.date,
    now: dt.datetime,
    version: str | None = None,
) -> tuple[bool, str]:
    """Apply ``downloads`` (file name -> bytes) to ``openapi_dir``; returns (changed, summary)."""
    old_docs: dict[str, Json] = {}
    new_docs: dict[str, Json] = {}
    changed_files: list[str] = []
    for name, data in downloads.items():
        new_docs[name] = check_openapi(name, data)
        path = openapi_dir / name
        old_bytes = path.read_bytes() if path.exists() else b"{}"
        old_docs[name] = json.loads(old_bytes)
        if old_bytes != data:
            changed_files.append(name)
    if not changed_files:
        return False, "No upstream change.\n"

    version = version or _version()
    remove_in = next_minor(version)
    overlay_path = openapi_dir / "overlay.json"
    overlay = json.loads(overlay_path.read_text("utf-8"))
    old_overlay = dict(overlay["operations"])
    deprecated_path = openapi_dir / "deprecated-operations.json"
    deprecated: dict[str, Any] = (
        json.loads(deprecated_path.read_text("utf-8"))
        if deprecated_path.exists()
        else {"description": "", "methods": {}}
    )
    deprecated.setdefault("methods", {})
    old_ops: dict[str, tuple[str, Json]] = {}
    new_ops: dict[str, tuple[str, Json]] = {}
    for name in downloads:
        for key, op in operations(old_docs[name], PREFIXES[name]).items():
            old_ops[key] = (name, op)
        for key, op in operations(new_docs[name], PREFIXES[name]).items():
            new_ops[key] = (name, op)

    def old_naming(key: str) -> Json:
        return old_ops[key][1].get("x-didit-sdk") or old_overlay.get(key)

    def new_naming(key: str) -> Json:
        return new_ops[key][1].get("x-didit-sdk") or old_overlay.get(key)

    added = sorted(set(new_ops) - set(old_ops))
    removed = sorted(set(old_ops) - set(new_ops))
    common = sorted(set(old_ops) & set(new_ops))
    # Server method name -> the operation that provides it after the sync.
    new_server_names = {
        _name(n): key for key in new_ops if (n := new_naming(key)) and n.get("server")
    }

    lines: list[str] = [
        f"Spec sync {today.isoformat()}. Upstream files changed: {', '.join(changed_files)}.",
        "",
    ]
    breaking: list[str] = []
    kept: list[str] = []

    def keep(naming: Json, key: str, reason: str, replacement: str | None) -> None:
        """Record a method that would disappear as deprecated until ``remove_in``."""
        doc_name, op = old_ops[key]
        method = _name(naming)
        if replacement:
            note = (
                f"Renamed to {replacement} on {today.isoformat()}; "
                f"this name is removed in version {remove_in}."
            )
        else:
            note = (
                f"Removed from the API contract on {today.isoformat()}; "
                f"this method is removed in version {remove_in}."
            )
        entry: dict[str, Any] = {
            "reason": reason,
            "operation_key": key,
            "x-didit-sdk": naming,
            "operation": dereference(old_docs[doc_name], op),
            "since": today.isoformat(),
            "deprecated_since": version,
            "remove_in": remove_in,
            "note": note,
        }
        if replacement:
            entry["replacement"] = replacement
        deprecated["methods"][method] = entry
        kept.append(method)

    lines.append(f"## Added operations ({len(added)})")
    for key in added:
        n = new_naming(key)
        if n is None:
            lines.append(
                f"- `{key}`: **no SDK naming**; add an entry to `openapi/overlay.json` (DESIGN section 4)"
            )
        elif n.get("server"):
            lines.append(f"- `{key}` -> `{_name(n)}`")
        else:
            lines.append(f"- `{key}` (not exposed by server SDKs: {n['auth']})")
    lines.append("")

    lines.append(f"## Removed operations ({len(removed)})")
    for key in removed:
        n = old_naming(key)
        if n is None:
            lines.append(f"- `{key}`")
        elif not n.get("server"):
            lines.append(f"- `{key}` (not exposed by server SDKs)")
        elif _name(n) in new_server_names:
            lines.append(
                f"- `{key}` moved to `{new_server_names[_name(n)]}`; `{_name(n)}` keeps its name"
            )
        else:
            breaking.append(
                f"`{_name(n)}` was removed upstream ({key}); kept as a deprecated method until "
                f"version {remove_in}"
            )
            lines.append(
                f"- `{key}` (`{_name(n)}`): kept as a deprecated method until version {remove_in}, "
                "recorded in `openapi/deprecated-operations.json`"
            )
            keep(n, key, "removed", None)
        overlay["operations"].pop(key, None)
    lines.append("")

    renames: list[str] = []
    for key in common:
        before, after = old_naming(key), new_naming(key)
        if not before or not before.get("server"):
            continue
        if after and after.get("server") and _name(after) == _name(before):
            continue
        if _name(before) in new_server_names:
            continue  # another operation now provides the name (swapped or moved)
        if after is None:
            renames.append(
                f"- `{key}` lost its SDK naming; `{_name(before)}` is kept as deprecated"
            )
            breaking.append(f"`{_name(before)}` ({key}) has no SDK naming any more")
            keep(before, key, "removed", None)
        elif not after.get("server"):
            renames.append(
                f"- `{key}` (`{_name(before)}`) is no longer a server operation "
                f"(auth {after.get('auth')}); kept as deprecated until version {remove_in}"
            )
            breaking.append(f"`{_name(before)}` ({key}) is no longer exposed to servers")
            keep(before, key, "removed", None)
        else:
            renames.append(
                f"- `{key}`: `{_name(before)}` renamed to `{_name(after)}`; the old name stays "
                f"as a deprecated alias until version {remove_in}"
            )
            breaking.append(
                f"`{_name(before)}` was renamed upstream to `{_name(after)}` ({key}); the old "
                f"name is a deprecated alias until version {remove_in}"
            )
            keep(before, key, "renamed", _name(after))
    lines.append(f"## Renamed methods ({len(renames)})")
    lines.extend(renames)
    lines.append("")

    for method in sorted(deprecated["methods"]):
        if method in new_server_names and method not in kept:
            del deprecated["methods"][method]
            lines.append(
                f"- `{method}` is provided again by `{new_server_names[method]}`; "
                "its deprecation entry was dropped."
            )

    changes: list[str] = []
    for key in common:
        old_name, old = old_ops[key]
        new_name, new = new_ops[key]
        if old == new and old_docs[old_name].get("components") == new_docs[new_name].get(
            "components"
        ):
            continue
        notes, is_breaking = describe_change(old_docs[old_name], old, new_docs[new_name], new)
        if old == new and notes == ["descriptions, examples or other details changed"]:
            continue
        marker = " **(breaking)**" if is_breaking else ""
        changes.append(f"- `{key}`{marker}: " + "; ".join(notes))
        if is_breaking:
            breaking.append(f"`{key}`: " + "; ".join(n for n in notes if n.endswith("(breaking)")))
    lines.append(f"## Changed operations ({len(changes)})")
    lines.extend(changes)
    lines.append("")

    lines.append("## Schemas")
    for name in downloads:
        old_schemas = old_docs[name].get("components", {}).get("schemas", {})
        new_schemas = new_docs[name].get("components", {}).get("schemas", {})
        gone = sorted(set(old_schemas) - set(new_schemas))
        for schema in gone:
            breaking.append(f"{name}: schema `{schema}` removed (its type leaves `didit.types`)")
        for label, names in (
            ("added", sorted(set(new_schemas) - set(old_schemas))),
            ("removed", gone),
            (
                "changed",
                sorted(
                    k
                    for k in set(old_schemas) & set(new_schemas)
                    if old_schemas[k] != new_schemas[k]
                ),
            ),
        ):
            if names:
                lines.append(f"- {name} {label}: " + ", ".join(f"`{n}`" for n in names))
    lines.append("")

    dropped: list[str] = []
    for key in list(overlay["operations"]):
        entry = new_ops.get(key)
        if entry is not None and entry[1].get("x-didit-sdk") is not None:
            if entry[1]["x-didit-sdk"] != overlay["operations"][key]:
                lines.append(
                    f"- `{key}`: upstream x-didit-sdk differs from the overlay; upstream wins."
                )
            dropped.append(key)
            del overlay["operations"][key]
    if dropped:
        lines.append(f"Dropped {len(dropped)} overlay entries that upstream now carries.")
        lines.append("")

    lines.insert(2, "## Breaking changes")
    lines.insert(3, "\n".join(f"- {b}" for b in breaking) if breaking else "None detected.")
    lines.insert(4, "")

    for name, data in downloads.items():
        (openapi_dir / name).write_bytes(data)
    source_path = openapi_dir / "SOURCE.json"
    source = json.loads(source_path.read_text("utf-8")) if source_path.exists() else {}
    for name, data in downloads.items():
        source[name] = {
            "url": UPSTREAM.get(name, source.get(name, {}).get("url", "")),
            "sha256": hashlib.sha256(data).hexdigest(),
            "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    # Same layout as the seeded files (one-space indent, no trailing newline), so diffs stay small.
    source_path.write_text(json.dumps(source, indent=1, ensure_ascii=False), "utf-8")
    overlay_path.write_text(json.dumps(overlay, indent=1, ensure_ascii=False), "utf-8")
    deprecated_path.write_text(json.dumps(deprecated, indent=1, ensure_ascii=False) + "\n", "utf-8")
    return True, "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--summary", type=pathlib.Path, help="write the Markdown summary here")
    parser.add_argument(
        "--from-dir", type=pathlib.Path, help="read the upstream files from a directory instead"
    )
    args = parser.parse_args(argv)
    if args.from_dir:
        downloads = {name: (args.from_dir / name).read_bytes() for name in UPSTREAM}
    else:
        downloads = {name: fetch(url) for name, url in UPSTREAM.items()}
    now = dt.datetime.now(dt.timezone.utc)
    try:
        changed, summary = sync(REPO / "openapi", downloads, today=now.date(), now=now)
    except SpecSyncError as exc:
        print(f"spec sync refused the download, nothing was written: {exc}", file=sys.stderr)
        return 1
    if args.summary:
        args.summary.write_text(summary, "utf-8")
    print(summary)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
            fh.write(f"date={now.date().isoformat()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
