"""The ``aiida:`` reader: ``load("aiida:1234")``, ``load("aiida://host/1234")``."""
from __future__ import annotations

from ewald.io.base import FrameReader

from . import frames as F
from . import transport
from .uri import parse


class AiidaReader(FrameReader):
    """AiiDA node by PK or UUID: ``aiida:[profile/]NODE[/link/...]``, or on another machine
    ``aiida://[user@]host[:port]/[profile/]NODE[/link/...]`` (read-only).

    ``what`` picks the view of a process (``trajectory``, ``phonons``, ``bands``,
    ``structures``, ``input``); by default the first it has. ``frames`` is the number of
    frames in one period of an animated phonon mode. ``python`` is the remote Python with
    aiida-core (default: the one ``verdi`` runs with).
    """

    schemes = ("aiida",)
    description = ("AiiDA node by PK/UUID (aiida:1234, aiida:profile/1234/link, aiida://host/1234): "
                   "structures, trajectories, bands, aiida-phonopy results, workflows; read-only")

    def __init__(self, path, what: str | None = None, profile: str | None = None, frames: int = 24,
                 python: str | None = None):
        self.path = str(path)
        self.what, self.profile, self.python = what, profile, python
        self.uri = parse(self.path)
        self.meta, self.arrays = transport.bundle(self.uri, what, profile, python)
        self.view = self.meta["view"]
        self._inner = None
        self._index: list = []          # (item number, frame within item)
        self._trajs: dict = {}
        items = self.meta["items"]
        if self.view == "trajectory":
            for k, item in enumerate(items):
                self._trajs[k] = F.Trajectory(item, self.arrays, f"{k}.")
                self._index += [(k, i) for i in range(len(self._trajs[k]))]
        elif self.view in ("structures", "input"):
            self._index = [(k, 0) for k in range(len(items))]
        elif self.view == "bands":
            self._index = [(0, 0)]
        else:
            self._inner = F.phonon_reader(items[-1], frames)
            self._index = [(len(items) - 1, i) for i in range(len(self._inner))]

    def __len__(self) -> int:
        return len(self._index)

    def read(self, index: int):
        k, i = self._index[index]
        item = self.meta["items"][k]
        if self.view == "trajectory":
            data = self._trajs[k].frame(i)
        elif self.view in ("structures", "input"):
            data = F.structure(item, self.arrays, f"{k}.")
        elif self.view == "bands":
            data = F.bands(item, self.arrays, f"{k}.")
        else:
            data = self._inner.read(i)
        for key, value in {**self.meta["scalars"], **item.get("scalars", {})}.items():
            data.attributes.setdefault(key, value)
        data.attributes["AiiDA"] = {**self.meta["node"], "uri": self.path, "view": self.view,
                                    "profile": self.meta["profile"], "host": self.uri.host,
                                    "output": item["label"] or None, "output_pk": item["pk"],
                                    "calc_pk": item["calc_pk"]}
        return data
