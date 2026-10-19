"""``aiida:[profile/]NODE[/link/...]`` strings and the profile they need."""
from __future__ import annotations

import re
from dataclasses import dataclass

_NODE = re.compile(r"^(\d+|[0-9a-fA-F-]{4,36})$")


@dataclass(frozen=True)
class AiidaURI:
    """``node`` is a PK (int) or a UUID / UUID prefix (str); ``links`` are output link labels
    (or labels of called processes) followed from that node; ``profile`` None is the default."""

    node: int | str
    links: tuple = ()
    profile: str | None = None

    def __str__(self) -> str:
        parts = ([self.profile] if self.profile else []) + [str(self.node), *self.links]
        return "aiida:" + "/".join(parts)


def parse(text: str) -> AiidaURI:
    """Parse ``aiida:1234``, ``aiida:prof/1234``, ``aiida:3f9c2e1a/relax/output_structure``.

    The first part is the node when it is a number or looks like a UUID (hex digits and
    dashes); otherwise it names the profile and the node follows.
    """
    if not text.lower().startswith("aiida:"):
        raise ValueError(f"not an aiida: path: {text!r}")
    parts = [p for p in text[len("aiida:"):].strip("/").split("/") if p]
    if not parts:
        raise ValueError("aiida: needs a node PK or UUID, e.g. aiida:1234")
    profile = None
    if not _NODE.match(parts[0]):
        profile, parts = parts[0], parts[1:]
        if not parts or not _NODE.match(parts[0]):
            raise ValueError(f"{text!r}: expected a PK or UUID after the profile name {profile!r}")
    node = int(parts[0]) if parts[0].isdigit() else parts[0].lower()
    return AiidaURI(node, tuple(parts[1:]), profile)


def load_profile(name: str | None = None):
    """Load AiiDA profile ``name`` (None: the default one) for reading; switching between
    profiles in one process is allowed. Raises a readable error when AiiDA is missing or
    has no such profile."""
    try:
        import aiida
    except ImportError as exc:  # pragma: no cover - the package depends on aiida-core
        raise ImportError("ewald-aiida needs aiida-core: pip install aiida-core") from exc
    current = aiida.get_profile()
    if current is not None and (name is None or current.name == name):
        return current
    try:
        return aiida.load_profile(name, allow_switch=True)
    except Exception as exc:  # ProfileConfigurationError, MissingConfigurationError, ...
        hint = "set one with `verdi profile set-default`" if name is None else "see `verdi profile list`"
        raise LookupError(f"cannot load AiiDA profile {name or '(default)'}: {exc}; {hint}") from exc
