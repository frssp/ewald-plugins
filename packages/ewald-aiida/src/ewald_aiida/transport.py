"""Run :mod:`ewald_aiida.export` where the AiiDA profile is: in this process, or over SSH.

On a remote host the exporter's source is sent as ``python -c`` (compressed, base64), so the
host needs only aiida-core (and phonopy for phonon results) in the Python that runs ``verdi``;
nothing is installed there. The connection is EWALD's own SSH layer (``ewald.io.remote``:
``~/.ssh/config`` aliases, keys, agent, jump hosts, known_hosts checks). Bundles are cached
under EWALD's remote cache by host, profile and node UUID.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import zlib

from . import export
from .uri import AiidaURI

_PYTHON: dict = {}  # host -> the remote python that runs verdi


def payload() -> str:
    """``python -c`` source that runs the exporter with the command-line arguments."""
    with open(export.__file__, "rb") as fh:
        code = base64.b64encode(zlib.compress(fh.read(), 9)).decode()
    return f"import base64,zlib;exec(compile(zlib.decompress(base64.b64decode('{code}')),'ewald_aiida_export','exec'))"


def command(python: str, args: list[str]) -> str:
    return " ".join([shlex.quote(python), "-c", shlex.quote(payload()), *map(shlex.quote, args)])


def _connection(uri: AiidaURI):
    from ewald.io import remote

    return remote._conn(remote.parse_remote(f"ssh://{uri.ssh_target}/"))


def run(uri: AiidaURI, args: list[str], python: str | None = None) -> bytes:
    """Run the exporter with ``args`` on ``uri``'s host; returns its stdout."""
    conn = _connection(uri)
    py = python or os.environ.get("EWALD_AIIDA_PYTHON") or remote_python(uri, conn)
    status, out = conn.run(command(py, args))
    if status != 0:
        if out.startswith(export.ERROR):
            raise LookupError(f"{uri} on {uri.host}: {out[len(export.ERROR):].decode(errors='replace')}")
        hint = (" (no aiida-core there? pass python='/path/to/env/bin/python' or set EWALD_AIIDA_PYTHON)"
                if status in (1, 126, 127) else "")
        raise RuntimeError(f"AiiDA exporter failed on {uri.host} with status {status}{hint}: "
                           f"{out[-500:].decode(errors='replace')}")
    return out


def remote_python(uri: AiidaURI, conn) -> str:
    """The Python of ``verdi`` on the host (its shebang, found through a login shell so conda
    and module setups apply), else ``python3``."""
    key = uri.ssh_target
    if key not in _PYTHON:
        status, out = conn.run("bash -lc 'head -1 \"$(command -v verdi)\"' 2>/dev/null")
        line = out.decode(errors="replace").strip()
        _PYTHON[key] = line[2:].strip().split()[0] if status == 0 and line.startswith("#!") and \
            "env" not in line.split()[0] else "python3"
    return _PYTHON[key]


def _args(uri: AiidaURI, what: str | None, profile: str | None) -> list[str]:
    out = ["bundle"]
    if profile or uri.profile:
        out += ["--profile", profile or uri.profile]
    if what:
        out += ["--what", what]
    return out + [str(uri.node), *uri.links]


def bundle(uri: AiidaURI, what: str | None = None, profile: str | None = None, python: str | None = None,
           cache: bool = True):
    """``(meta, arrays)`` of :func:`ewald_aiida.export.bundle` for ``uri``, local or remote."""
    if uri.host is None:
        return export.bundle(uri.node, uri.links, what, profile or uri.profile)
    path = _cache_path(uri, what, profile)
    if cache and path and os.path.exists(path):
        with open(path, "rb") as fh:
            return export.from_npz(fh.read())
    blob = run(uri, _args(uri, what, profile), python)
    meta, arrays = export.from_npz(blob)
    if cache and path and _finished(meta):  # a running workflow may still grow
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "wb") as fh:
            fh.write(blob)
        os.replace(path + ".tmp", path)
    return meta, arrays


def _finished(meta) -> bool:
    node = meta["node"]
    return "process_state" not in node or node["process_state"] in ("finished", "excepted", "killed")


def _cache_path(uri: AiidaURI, what, profile) -> str | None:
    if not isinstance(uri.node, str) or len(uri.node) < 32:
        return None  # a PK or a UUID prefix may name another node tomorrow; only full UUIDs are cached
    from ewald.io import remote

    key = hashlib.sha1(json.dumps([uri.ssh_target, profile or uri.profile, uri.node, uri.links, what]).encode())
    return str(remote.cache_dir() / "aiida" / (key.hexdigest()[:20] + ".npz"))


def tree(uri: AiidaURI, profile: str | None = None, depth: int = 4, python: str | None = None) -> str:
    if uri.host is None:
        return export.tree(uri.node, profile or uri.profile, depth, uri.links)
    args = ["tree", "--depth", str(depth)] + (["--profile", profile or uri.profile] if profile or uri.profile else [])
    return run(uri, args + [str(uri.node), *uri.links], python).decode()


def find(host: AiidaURI | None, process_label=None, profile=None, limit=20, finished_ok=None, python=None):
    if host is None or host.host is None:
        return export.find(process_label, profile, limit, finished_ok)
    args = ["find", "--limit", str(limit)] + (["--profile", profile] if profile else []) + \
           (["--process", process_label] if process_label else []) + (["--ok"] if finished_ok else [])
    return json.loads(run(host, args, python))
