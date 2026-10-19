"""Check every entry in plugins/*.toml and write index.json, the catalog EWALD reads.

    python scripts/build_index.py            # check and write index.json
    python scripts/build_index.py --check    # check only; exit 1 if index.json is stale

An entry is one TOML file named after the plugin id. Required keys: id, name, summary, kinds,
source, version. Optional: requires_ewald, author, homepage, description, tests.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("modifier", "reader", "writer", "visual", "overlay", "colormap", "theme", "tool")
REQUIRED = ("id", "name", "summary", "kinds", "source", "version")
OPTIONAL = ("requires_ewald", "author", "homepage", "description", "tests")
FORMAT = 1
# a source is pinned: a git URL at a tag or commit, a PyPI release, or a raw file at a tag or commit
_GIT = re.compile(r"pip:git\+https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?@([\w.\-/]+)(?:#.*)?$")
_PYPI = re.compile(r"pip:[A-Za-z0-9][\w.-]*(?:\[[\w,.-]+\])?==[\w.!+-]+$")
_RAW = re.compile(r"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/([\w.\-]+)/.+\.py$")
_BRANCHES = {"main", "master", "develop", "dev", "HEAD"}
_REQUIREMENT = re.compile(r"\s*(~=|==|!=|>=|<=|>|<)?\s*\d+(\.\d+)*\s*")


def check_entry(path: Path) -> tuple[dict, list[str]]:
    problems = []
    try:
        entry = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"{path.name}: not valid TOML: {exc}"]
    for key in REQUIRED:
        if not entry.get(key):
            problems.append(f"{path.name}: missing {key!r}")
    for key in entry:
        if key not in REQUIRED + OPTIONAL:
            problems.append(f"{path.name}: unknown key {key!r} (allowed: {', '.join(REQUIRED + OPTIONAL)})")
    pid = str(entry.get("id", ""))
    if pid and path.stem != pid:
        problems.append(f"{path.name}: file name must be the id ({pid}.toml)")
    if pid and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", pid):
        problems.append(f"{path.name}: id must be lower case letters, digits, '_', '-' or '.'")
    kinds = entry.get("kinds", [])
    if not isinstance(kinds, list) or not all(k in KINDS for k in kinds):
        problems.append(f"{path.name}: kinds must be a list from {', '.join(KINDS)}")
    source = str(entry.get("source", ""))
    if source:
        m = _GIT.match(source) or _RAW.match(source)
        if not (m or _PYPI.match(source)):
            problems.append(f"{path.name}: source must be pip:git+https://github.com/OWNER/REPO@TAG, "
                            f"pip:NAME==VERSION or a raw.githubusercontent.com .py file at a tag or commit")
        elif m and m.group(1) in _BRANCHES:
            problems.append(f"{path.name}: source points at the branch {m.group(1)!r}; pin a tag or commit")
    req = entry.get("requires_ewald", "")
    if req and not all(_REQUIREMENT.fullmatch(c) for c in str(req).split(",")):
        problems.append(f"{path.name}: requires_ewald {req!r} is not like '>=0.1, <1'")
    return entry, problems


def build(root: Path = ROOT) -> tuple[dict, list[str]]:
    entries, problems = [], []
    for path in sorted((root / "plugins").glob("*.toml")):
        entry, errs = check_entry(path)
        problems += errs
        if not errs:
            entries.append({k: entry[k] for k in REQUIRED + OPTIONAL if k in entry})
    return {"format": FORMAT, "plugins": entries}, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="do not write; fail if index.json differs")
    args = ap.parse_args(argv)
    index, problems = build()
    for p in problems:
        print("ERROR", p)
    if problems:
        return 1
    text = json.dumps(index, indent=1, ensure_ascii=False) + "\n"
    target = ROOT / "index.json"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print("index.json is stale: run python scripts/build_index.py and commit it")
            return 1
        print(f"index.json is up to date ({len(index['plugins'])} plugins)")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"wrote index.json ({len(index['plugins'])} plugins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
