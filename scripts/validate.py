"""Install index entries into a scratch ewald config and check that ewald loads them.

    python scripts/validate.py                  # every entry
    python scripts/validate.py cell_axes        # some entries
    python scripts/validate.py --changed origin/main   # entries changed since a git ref

For each entry: fetch or pip-install its source, load ewald's plugins with an empty config
folder, and check that the plugin is loaded, needs an ewald version that is installed, and
registers something of every kind it lists. If ``tests`` names a test file (same source rules
as ``source``), it is run with pytest. pip sources are installed into the running Python, so
run this in a throwaway virtualenv (CI does).

Private sources: set GITHUB_TOKEN (CI uses the EWALD_TOKEN secret). With ``--from-git
OWNER/REPO=PATH`` raw.githubusercontent.com files of that repository are read from a local
clone with ``git show`` instead.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import ROOT, check_entry  # noqa: E402

_RAW = re.compile(r"https://raw\.githubusercontent\.com/([\w.-]+/[\w.-]+)/([\w.\-]+)/(.+)$")
_PLURAL = {"modifier": "modifiers", "reader": "readers", "writer": "writers", "visual": "visuals",
           "overlay": "overlays", "colormap": "colormaps", "theme": "themes", "tool": "tools", "ui_theme": "ui_themes",
           "ai_provider": "ai_providers", "settings_page": "settings_pages", "panel": "panels",
           "workflow_source": "workflows"}


def fetch(url: str, local: dict) -> bytes:
    m = _RAW.match(url)
    if m and m.group(1) in local:
        return subprocess.run(["git", "-C", local[m.group(1)], "show", f"{m.group(2)}:{m.group(3)}"],
                              check=True, capture_output=True).stdout
    req = urllib.request.Request(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(("https://raw.githubusercontent.com/", "https://api.github.com/")):
        req.add_header("Authorization", f"token {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _pip_url(source: str) -> str:
    spec = source[len("pip:"):]
    token = os.environ.get("GITHUB_TOKEN")
    if token and spec.startswith("git+https://github.com/"):
        spec = spec.replace("https://", f"https://x-access-token:{token}@", 1)
    return spec


_PROBE = """
import json, sys
from ewald import plugins
print(json.dumps({"plugins": {k: p.as_dict() for k, p in plugins.installed().items()},
                  "version": plugins.ewald_version()}))
"""


def validate(entry: dict, local: dict) -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, EWALD_CONFIG_DIR=tmp)
        folder = Path(tmp, "plugins")
        folder.mkdir()
        source = entry["source"]
        if source.startswith("pip:"):
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", _pip_url(source)],
                               capture_output=True, text=True)
            if r.returncode:
                return [f"pip install failed: {r.stderr.strip()[-600:]}"]
        else:
            data = fetch(source, local)
            if entry.get("sha256") and hashlib.sha256(data).hexdigest() != entry["sha256"]:
                return [f"sha256 of the fetched file is {hashlib.sha256(data).hexdigest()}, not {entry['sha256']}"]
            (folder / source.rsplit("/", 1)[-1]).write_bytes(data)
        r = subprocess.run([sys.executable, "-I", "-c", _PROBE], capture_output=True, text=True, env=env, cwd=tmp)
        if r.returncode:
            return [f"loading ewald plugins failed: {r.stderr.strip()[-600:]}"]
        probe = json.loads(r.stdout)
        found = probe["plugins"]
        stem = source.rsplit("/", 1)[-1].removesuffix(".py")
        plugin = found.get(entry["id"]) or found.get(stem)
        if plugin is None and source.startswith("pip:"):   # a package without an ewald.plugins manifest
            plugin = next(iter(found.values()), None) if len(found) == 1 else None
        if plugin is None:
            return [f"no installed plugin with id {entry['id']!r} (found: {', '.join(found) or 'none'})"]
        if plugin["id"] != entry["id"]:
            problems.append(f"the plugin calls itself {plugin['id']!r}; set id = {plugin['id']!r} here "
                            f"or the same id in its manifest")
        if plugin["state"] != "loaded":
            problems.append(f"plugin is {plugin['state']}: {'; '.join(plugin['errors'])}")
        for kind in entry["kinds"]:
            if kind in _PLURAL and not plugin["contributions"].get(_PLURAL[kind]):
                problems.append(f"lists kind {kind!r} but registers no {_PLURAL[kind]}")
        if entry.get("tests"):
            test = Path(tmp, "test_entry.py")
            test.write_bytes(fetch(entry["tests"], local))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test)],
                               capture_output=True, text=True, env=env, cwd=tmp)
            if r.returncode:
                problems.append("tests failed:\n" + r.stdout[-1500:])
    return problems


def changed_ids(ref: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", ref, "--", "plugins"],
                         check=True, capture_output=True, text=True).stdout.split()
    return [Path(p).stem for p in out if p.endswith(".toml") and (ROOT / p).exists()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--changed", metavar="REF", help="only entries changed since this git ref")
    ap.add_argument("--from-git", action="append", default=[], metavar="OWNER/REPO=PATH")
    args = ap.parse_args(argv)
    local = dict(item.split("=", 1) for item in args.from_git)
    ids = args.ids or (changed_ids(args.changed) if args.changed else
                       [p.stem for p in sorted((ROOT / "plugins").glob("*.toml"))])
    failed = 0
    for pid in ids:
        entry, problems = check_entry(ROOT / "plugins" / f"{pid}.toml")
        problems = problems or validate(entry, local)
        print(("FAIL " if problems else "ok   ") + pid)
        for p in problems:
            print("     " + p.replace("\n", "\n     "))
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
