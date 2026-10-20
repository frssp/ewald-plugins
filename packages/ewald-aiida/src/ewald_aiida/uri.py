"""``aiida:[profile/]NODE[/link/...]`` and ``aiida://[user@]host[:port]/[profile/]NODE[/link/...]``."""
from __future__ import annotations

import re
from dataclasses import dataclass

_NODE = re.compile(r"^(\d+|[0-9a-fA-F-]{4,36})$")
_HOST = re.compile(r"^(?:(?P<user>[^@/:\s]+)@)?(?P<host>\[[^\]]+\]|[^@/:\s]+)(?::(?P<port>\d+))?$")


@dataclass(frozen=True)
class AiidaURI:
    """``node`` is a PK (int) or a UUID / UUID prefix (str); ``links`` are output link labels
    (or labels of called processes) followed from that node; ``profile`` None is the default.
    ``host`` (an SSH host, ``~/.ssh/config`` alias or EWALD remote profile) means the AiiDA
    profile lives on that machine."""

    node: int | str
    links: tuple = ()
    profile: str | None = None
    host: str | None = None
    user: str | None = None
    port: int | None = None

    def __str__(self) -> str:
        parts = ([self.profile] if self.profile else []) + [str(self.node), *self.links]
        if self.host is None:
            return "aiida:" + "/".join(parts)
        return f"aiida://{self.ssh_target}/" + "/".join(parts)

    @property
    def ssh_target(self) -> str:
        return (f"{self.user}@" if self.user else "") + self.host + (f":{self.port}" if self.port else "")


def parse(text: str) -> AiidaURI:
    """Parse ``aiida:1234``, ``aiida:prof/1234``, ``aiida:3f9c2e1a/relax/output_structure``,
    ``aiida://alice@cluster/prof/1234``.

    The first path part is the node when it is a number or looks like a UUID (hex digits and
    dashes); otherwise it names the profile and the node follows.
    """
    if not text.lower().startswith("aiida:"):
        raise ValueError(f"not an aiida: path: {text!r}")
    rest = text[len("aiida:"):]
    host = user = port = None
    if rest.startswith("//"):
        target, _, rest = rest[2:].partition("/")
        m = _HOST.match(target)
        if not m:
            raise ValueError(f"{text!r}: expected aiida://[user@]host[:port]/NODE")
        host, user = m["host"].strip("[]"), m["user"]
        port = int(m["port"]) if m["port"] else None
    parts = [p for p in rest.strip("/").split("/") if p]
    if not parts:
        raise ValueError("aiida: needs a node PK or UUID, e.g. aiida:1234")
    profile = None
    if not _NODE.match(parts[0]):
        profile, parts = parts[0], parts[1:]
        if not parts or not _NODE.match(parts[0]):
            raise ValueError(f"{text!r}: expected a PK or UUID after the profile name {profile!r}")
    node = int(parts[0]) if parts[0].isdigit() else parts[0].lower()
    return AiidaURI(node, tuple(parts[1:]), profile, host, user, port)
