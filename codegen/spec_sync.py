#!/usr/bin/env python3
"""Sync ``openapi/`` with the published API contract (docs/DESIGN.md section 3.1).

    uv run python codegen/spec_sync.py --summary spec-sync-summary.md

Downloads https://docs.didit.me/openapi-25.json and openapi-auth.json, and when
either changed:

- writes them byte for byte to ``openapi/verification.json`` / ``account.json``
  and records URL, SHA-256 and fetch time in ``openapi/SOURCE.json``;
- drops ``overlay.json`` entries that upstream now carries as ``x-didit-sdk``;
- records every removed operation, fully dereferenced, in
  ``openapi/deprecated-operations.json`` so the SDK keeps (and deprecates) its
  method for one more minor version; an operation whose SDK name reappears on
  another path counts as moved, not removed;
- writes a Markdown summary of added, removed and changed operations and
  schemas, calling out what is breaking.

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
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
Json = Any


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "didit-sdk-python spec-sync"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URLs
        data: bytes = response.read()
    json.loads(data)  # refuse anything that is not JSON
    return data


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
            target = dereference(doc, _pointer(doc, node["$ref"]), depth + 1)
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


def _props(doc: Json, schema: Json) -> tuple[set[str], set[str]]:
    schema = dereference(doc, schema)
    props: set[str] = set()
    required: set[str] = set()
    stack = [schema]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        props |= set(cur.get("properties", {}))
        required |= set(cur.get("required", []))
        stack.extend(cur.get("allOf", []))
    return props, required


def _body_schema(op: Json) -> Json:
    content = (op.get("requestBody") or {}).get("content", {})
    media = content.get("application/json") or content.get("multipart/form-data") or {}
    return media.get("schema", {})


def _success_schema(op: Json) -> Json:
    for code, response in sorted(op.get("responses", {}).items()):
        if str(code).startswith("2"):
            media = (response.get("content") or {}).get("application/json") or {}
            return media.get("schema", {})
    return {}


def describe_change(old_doc: Json, old: Json, new_doc: Json, new: Json) -> tuple[list[str], bool]:
    """Human-readable differences of one operation, and whether any is breaking."""
    notes: list[str] = []
    breaking = False
    old_params = {(p.get("in"), p.get("name")): p for p in dereference(old_doc, old.get("parameters", []))}
    new_params = {(p.get("in"), p.get("name")): p for p in dereference(new_doc, new.get("parameters", []))}
    for key in sorted(set(old_params) - set(new_params), key=str):
        notes.append(f"parameter removed: {key[1]} ({key[0]})")
        breaking = True
    for key in sorted(set(new_params) - set(old_params), key=str):
        required = bool(new_params[key].get("required"))
        notes.append(f"parameter added: {key[1]} ({key[0]}{', required' if required else ''})")
        breaking = breaking or required
    for key in sorted(set(old_params) & set(new_params), key=str):
        if not old_params[key].get("required") and new_params[key].get("required"):
            notes.append(f"parameter now required: {key[1]}")
            breaking = True
    old_props, old_req = _props(old_doc, _body_schema(old))
    new_props, new_req = _props(new_doc, _body_schema(new))
    for name in sorted(old_props - new_props):
        notes.append(f"body field removed: {name}")
        breaking = True
    for name in sorted(new_props - old_props):
        notes.append(f"body field added: {name}{' (required)' if name in new_req else ''}")
        breaking = breaking or name in new_req
    for name in sorted((new_req - old_req) & old_props):
        notes.append(f"body field now required: {name}")
        breaking = True
    old_resp, _ = _props(old_doc, _success_schema(old))
    new_resp, _ = _props(new_doc, _success_schema(new))
    for name in sorted(old_resp - new_resp):
        notes.append(f"response field removed: {name}")
        breaking = True
    for name in sorted(new_resp - old_resp):
        notes.append(f"response field added: {name}")
    if old.get("x-didit-sdk") != new.get("x-didit-sdk") and new.get("x-didit-sdk") is not None:
        notes.append(f"x-didit-sdk now {json.dumps(new['x-didit-sdk'], sort_keys=True)}")
    if not notes:
        notes.append("descriptions, examples or other details changed")
    return notes, breaking


def _version() -> str:
    text = (REPO / "src" / "didit" / "_version.py").read_text("utf-8")
    match = re.search(r'__version__ = "([^"]+)"', text)
    return match.group(1) if match else "unknown"


def sync(
    openapi_dir: pathlib.Path,
    downloads: dict[str, bytes],
    *,
    today: dt.date,
    now: dt.datetime,
) -> tuple[bool, str]:
    """Apply ``downloads`` (file name -> bytes) to ``openapi_dir``; returns (changed, summary)."""
    old_docs: dict[str, Json] = {}
    new_docs: dict[str, Json] = {}
    changed_files: list[str] = []
    for name, data in downloads.items():
        path = openapi_dir / name
        old_bytes = path.read_bytes() if path.exists() else b"{}"
        old_docs[name] = json.loads(old_bytes)
        new_docs[name] = json.loads(data)
        if old_bytes != data:
            changed_files.append(name)
    if not changed_files:
        return False, "No upstream change.\n"

    prefixes = {"verification.json": "", "account.json": "account "}
    overlay_path = openapi_dir / "overlay.json"
    overlay = json.loads(overlay_path.read_text("utf-8"))
    deprecated_path = openapi_dir / "deprecated-operations.json"
    deprecated: dict[str, Any] = (
        json.loads(deprecated_path.read_text("utf-8"))
        if deprecated_path.exists()
        else {"description": "", "operations": {}}
    )
    old_ops: dict[str, tuple[str, Json]] = {}
    new_ops: dict[str, tuple[str, Json]] = {}
    for name in downloads:
        for key, op in operations(old_docs[name], prefixes[name]).items():
            old_ops[key] = (name, op)
        for key, op in operations(new_docs[name], prefixes[name]).items():
            new_ops[key] = (name, op)

    def naming(key: str, op: Json) -> Json:
        return op.get("x-didit-sdk") or overlay["operations"].get(key)

    added = sorted(set(new_ops) - set(old_ops))
    removed = sorted(set(old_ops) - set(new_ops))
    common = sorted(set(old_ops) & set(new_ops))
    new_names = {
        (n["resource"], n["method"]): key for key, (_, op) in new_ops.items() if (n := naming(key, op))
    }

    lines: list[str] = [f"Spec sync {today.isoformat()}. Upstream files changed: {', '.join(changed_files)}.", ""]
    breaking: list[str] = []

    lines.append(f"## Added operations ({len(added)})")
    for key in added:
        n = naming(key, new_ops[key][1])
        if n is None:
            lines.append(f"- `{key}`: **no SDK naming**; add an entry to `openapi/overlay.json` (DESIGN section 4)")
        elif n.get("server"):
            lines.append(f"- `{key}` -> `{n['resource']}.{n['method']}`")
        else:
            lines.append(f"- `{key}` (not exposed by server SDKs: {n['auth']})")
    lines.append("")

    lines.append(f"## Removed operations ({len(removed)})")
    for key in removed:
        name, op = old_ops[key]
        n = naming(key, op)
        if n is None:
            lines.append(f"- `{key}`")
            continue
        moved_to = new_names.get((n["resource"], n["method"]))
        if moved_to:
            lines.append(f"- `{key}` moved to `{moved_to}`; `{n['resource']}.{n['method']}` keeps its name")
        elif n.get("server"):
            breaking.append(f"`{n['resource']}.{n['method']}` was removed upstream ({key})")
            lines.append(
                f"- `{key}` (`{n['resource']}.{n['method']}`): kept as a deprecated method for one minor "
                "version, recorded in `openapi/deprecated-operations.json`"
            )
            deprecated["operations"][key] = {
                "x-didit-sdk": n,
                "operation": dereference(old_docs[name], op),
                "removed_on": today.isoformat(),
                "deprecated_since": _version(),
                "note": f"Removed from the API contract on {today.isoformat()}; this method will be deleted in the next minor version.",
            }
        else:
            lines.append(f"- `{key}` (not exposed by server SDKs)")
        overlay["operations"].pop(key, None)
    lines.append("")

    for key in list(deprecated["operations"]):
        if key in new_ops:
            del deprecated["operations"][key]
            lines.append(f"- `{key}` is back upstream; its deprecation entry was dropped.")

    changes: list[str] = []
    for key in common:
        old_name, old = old_ops[key]
        new_name, new = new_ops[key]
        if old == new and old_docs[old_name].get("components") == new_docs[new_name].get("components"):
            continue
        notes, is_breaking = describe_change(old_docs[old_name], old, new_docs[new_name], new)
        if old == new and notes == ["descriptions, examples or other details changed"]:
            continue
        marker = " **(breaking)**" if is_breaking else ""
        changes.append(f"- `{key}`{marker}: " + "; ".join(notes))
        if is_breaking:
            breaking.append(f"`{key}`: " + "; ".join(notes))
    lines.append(f"## Changed operations ({len(changes)})")
    lines.extend(changes)
    lines.append("")

    lines.append("## Schemas")
    for name in downloads:
        old_schemas = old_docs[name].get("components", {}).get("schemas", {})
        new_schemas = new_docs[name].get("components", {}).get("schemas", {})
        for label, names in (
            ("added", sorted(set(new_schemas) - set(old_schemas))),
            ("removed", sorted(set(old_schemas) - set(new_schemas))),
            ("changed", sorted(k for k in set(old_schemas) & set(new_schemas) if old_schemas[k] != new_schemas[k])),
        ):
            if names:
                lines.append(f"- {name} {label}: " + ", ".join(f"`{n}`" for n in names))
    lines.append("")

    dropped: list[str] = []
    for key in list(overlay["operations"]):
        entry = new_ops.get(key)
        if entry is not None and entry[1].get("x-didit-sdk") is not None:
            if entry[1]["x-didit-sdk"] != overlay["operations"][key]:
                lines.append(f"- `{key}`: upstream x-didit-sdk differs from the overlay; upstream wins.")
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", type=pathlib.Path, help="write the Markdown summary here")
    parser.add_argument("--from-dir", type=pathlib.Path, help="read the upstream files from a directory instead")
    args = parser.parse_args(argv)
    if args.from_dir:
        downloads = {name: (args.from_dir / name).read_bytes() for name in UPSTREAM}
    else:
        downloads = {name: fetch(url) for name, url in UPSTREAM.items()}
    now = dt.datetime.now(dt.timezone.utc)
    changed, summary = sync(REPO / "openapi", downloads, today=now.date(), now=now)
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

