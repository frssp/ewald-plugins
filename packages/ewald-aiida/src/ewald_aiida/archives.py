"""AiiDA archives (``.aiida``) as read-only profiles: ``open_archive("wf.aiida")`` -> a profile
name such as ``archive-3f9c2e1a7b6d5e4f`` that every ``aiida:`` path takes
(``load("aiida:archive-3f9c2e1a7b6d5e4f/1234")``), with no database server.

An archive is extracted once into EWALD's cache, by the SHA-256 of its bytes, and opened there
as a folder. Opening the zip itself would make AiiDA copy the database to a temporary file that
it cannot delete on Windows (the file handle and the connection pool stay open: ``WinError
32``), so the folder is the only way that behaves the same on every platform. An archive written
by an older AiiDA is migrated on the way in; one from a newer AiiDA is refused with the version
to upgrade to.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile

from . import export

PREFIX = "archive-"
#: marker written last into a finished extraction, so a half-extracted folder is never opened
READY = ".ewald-ready"


def cache_root() -> str:
    from ewald.io import remote

    return str(remote.cache_dir() / "aiida-archives")


def _digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def open_archive(path) -> str:
    """Extract (once) and register the archive at ``path``; returns its profile name."""
    path = os.fspath(path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"{path}: not an AiiDA archive (.aiida is a zip file)")
    name = PREFIX + _digest(path)
    folder = os.path.join(cache_root(), name)
    if not os.path.exists(os.path.join(folder, READY)):
        _extract(path, folder)
    export.ARCHIVES[name] = folder
    return name


def resolve(profile: str | None) -> None:
    """Register ``profile`` if it names an archive extracted in an earlier session."""
    if not profile or not profile.startswith(PREFIX) or profile in export.ARCHIVES:
        return
    folder = os.path.join(cache_root(), profile)
    if not os.path.exists(os.path.join(folder, READY)):
        raise LookupError(f"AiiDA archive {profile} is not in the cache any more; open its .aiida file again")
    export.ARCHIVES[profile] = folder


def _extract(path: str, folder: str) -> None:
    from aiida.tools.archive.abstract import get_format

    os.makedirs(os.path.dirname(folder), exist_ok=True)
    work = tempfile.mkdtemp(prefix=".partial-", dir=os.path.dirname(folder))
    try:
        fmt = get_format()
        source = path
        version, latest = fmt.read_version(path), fmt.latest_version
        if version != latest:
            source = os.path.join(work, "migrated.aiida")
            try:
                fmt.migrate(path, source, latest)
            except Exception as exc:
                raise LookupError(f"{path}: archive version {version} cannot be read by this aiida-core "
                                  f"(schema {latest}); if it was written by a newer AiiDA, upgrade "
                                  f"aiida-core here: {exc}") from exc
        target = os.path.join(work, "archive")
        with zipfile.ZipFile(source) as z:
            z.extractall(target)
        with open(os.path.join(target, READY), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"source": os.path.basename(path), "version": version}, fh)
        if os.path.exists(folder):     # a half-extracted folder from an interrupted run
            shutil.rmtree(folder, ignore_errors=True)
        os.replace(target, folder)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def retrieved_file(profile: str, calc, name: str) -> str:
    """Local path of the retrieved file ``name`` of CalcJob ``calc`` (PK or UUID) in an archive
    profile, copied out of the archive once and named as it was, so EWALD's readers know it.
    A workflow step (a restart workchain around its calculations) reads its last CalcJob."""
    from aiida import orm

    resolve(profile)
    node = export.load(calc, (), profile)
    if not isinstance(node, orm.CalcJobNode):
        jobs = [n for n in export.descendants(node) if isinstance(n, orm.CalcJobNode)] \
            if export.is_process(node) else []
        node = jobs[-1] if jobs else node
    if not isinstance(node, orm.CalcJobNode) or name not in export.retrieved_files(node):
        raise FileNotFoundError(f"{calc} in {profile} has no retrieved file {name!r}")
    target = os.path.join(export.ARCHIVES[profile], "files", node.uuid, *name.split("/"))
    if not os.path.exists(target):
        folder = next(t.node for t in export.outgoing(node) if t.link_label == "retrieved")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        partial = target + ".partial"
        with folder.base.repository.open(name, "rb") as src, open(partial, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        os.replace(partial, target)
    return target


def root(profile: str):
    """PK of the process nobody called in an archive profile (the node it was made of); the
    newest one when an archive holds several."""
    resolve(profile)
    export.load_profile(profile)
    from aiida import orm

    qb = orm.QueryBuilder().append(orm.ProcessNode, tag="p").order_by({"p": {"ctime": "desc"}})
    for (node,) in qb.iterall():
        if node.caller is None:
            return node.pk
    raise LookupError(f"{profile}: no process in this archive")
