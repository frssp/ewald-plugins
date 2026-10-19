"""Browse the provenance graph: :func:`tree` and :func:`find`, local or on a remote host."""
from __future__ import annotations

from . import transport
from .uri import AiidaURI, parse


def _uri(identifier) -> AiidaURI:
    text = str(identifier)
    return parse(text if text.startswith("aiida:") else f"aiida:{text}")


def tree(identifier, profile: str | None = None, depth: int = 4, python: str | None = None) -> str:
    """Text tree of a process (``1234``, a UUID, ``aiida:prof/1234`` or ``aiida://host/1234``):
    the processes it called and their outputs, with PKs, and what ``load`` opens."""
    return transport.tree(_uri(identifier), profile, depth, python)


def find(process_label: str | None = None, profile: str | None = None, limit: int = 20,
         finished_ok: bool | None = None, host: str | None = None, python: str | None = None) -> list[dict]:
    """Recent processes, newest first: ``[{"pk", "uuid", "process_label", "state", "exit_status",
    "ctime", "label", "uri"}]``. ``process_label`` matches exactly or with ``%`` wildcards;
    ``host`` (``[user@]host[:port]``) searches the profile on that machine."""
    target = parse(f"aiida://{host}/0") if host else None
    rows = transport.find(target, process_label, profile, limit, finished_ok, python)
    base = f"aiida://{target.ssh_target}/" if target else "aiida:"
    for r in rows:
        r["uri"] = base + (f"{profile}/" if profile else "") + str(r["pk"])
    return rows
