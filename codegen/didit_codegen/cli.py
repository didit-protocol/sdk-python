"""``python codegen/generate.py [--check]``: regenerate the SDK from ``openapi/``."""

from __future__ import annotations

import argparse
import difflib
import filecmp
import pathlib
import shutil
import subprocess
import sys
import tempfile

from .generate import GENERATED_ROOTS, generate
from .spec import CodegenError

REPO = pathlib.Path(__file__).resolve().parents[2]


def _format(root: pathlib.Path) -> None:
    ruff = shutil.which("ruff")
    if ruff is None:
        raise CodegenError("ruff is needed to format the generated code: run `uv sync` first.")
    config = str(REPO / "pyproject.toml")
    subprocess.run([ruff, "check", "--config", config, "--select", "I", "--fix", "--quiet", str(root)], check=True)
    subprocess.run([ruff, "format", "--config", config, "--quiet", str(root)], check=True)


def write_tree(target: pathlib.Path) -> int:
    files = generate(REPO / "openapi")
    for rel, text in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _format(target)
    return len(files)


def _diff(expected: pathlib.Path, actual: pathlib.Path) -> list[str]:
    problems: list[str] = []
    for root in GENERATED_ROOTS:
        exp_root, act_root = expected / root, actual / root
        exp = {p.relative_to(exp_root) for p in exp_root.rglob("*") if p.is_file()} if exp_root.exists() else set()
        act = (
            {p.relative_to(act_root) for p in act_root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
            if act_root.exists()
            else set()
        )
        for rel in sorted(exp - act):
            problems.append(f"missing: {root}/{rel}")
        for rel in sorted(act - exp):
            problems.append(f"not generated (delete it): {root}/{rel}")
        for rel in sorted(exp & act):
            if not filecmp.cmp(exp_root / rel, act_root / rel, shallow=False):
                problems.append(f"stale: {root}/{rel}")
                if len(problems) < 5:
                    diff = difflib.unified_diff(
                        (act_root / rel).read_text("utf-8").splitlines(),
                        (exp_root / rel).read_text("utf-8").splitlines(),
                        "committed",
                        "generated",
                        lineterm="",
                        n=1,
                    )
                    problems.extend("    " + line for line in list(diff)[:40])
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed code is stale")
    args = parser.parse_args(argv)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            count = write_tree(out)
            if args.check:
                problems = _diff(out, REPO)
                if problems:
                    print("Generated code is stale. Run `uv run python codegen/generate.py`.\n")
                    print("\n".join(problems[:200]))
                    return 1
                print(f"Generated code is up to date ({count} files).")
                return 0
            for root in GENERATED_ROOTS:
                shutil.rmtree(REPO / root, ignore_errors=True)
                shutil.copytree(out / root, REPO / root)
            print(f"Wrote {count} generated files.")
            return 0
    except CodegenError as exc:
        print(f"codegen: {exc}", file=sys.stderr)
        return 2
