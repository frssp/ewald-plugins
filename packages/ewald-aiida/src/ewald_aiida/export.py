"""Read AiiDA nodes into plain arrays: the part of ewald-aiida that runs where the database is.

This module imports only the standard library, numpy and aiida-core (phonopy for phonon
results), never ewald, so the same code runs in-process for a local profile and on a remote
machine over SSH, sent as the source of ``python -c`` (see :mod:`ewald_aiida.transport`):

    python -c "<this file>" bundle [--profile P] [--what V] NODE [LINK ...]   # npz on stdout
    python -c "<this file>" tree [--profile P] [--depth D] NODE                # text
    python -c "<this file>" find [--profile P] [--process L] [--limit N] [--ok] # JSON

Everything here only reads: no node is stored, changed or submitted.

A bundle is ``(meta, arrays)``: ``meta`` is JSON (the node, the view, scalars of its ``Dict``
outputs, one entry per item), ``arrays`` maps ``"<item>.<name>"`` to numpy arrays.
"""
from __future__ import annotations

import io
import json
import sys

import numpy as np

VIEWS = ("trajectory", "phonons", "bands", "structures", "input")
PER_ATOM = {"forces": "Force", "force": "Force", "velocities": "Velocity", "velocity": "Velocity",
            "charges": "Charge", "magnetic_moments": "Magnetic Moment"}
_TRAJ_ARRAYS = {"positions", "cells", "steps", "times", "symbols"}


# ----------------------------------------------------------------------- profile and nodes
def load_profile(name=None):
    """Load AiiDA profile ``name`` (None: the default one) for reading."""
    import aiida

    current = aiida.get_profile()
    if current is not None and (name is None or current.name == name):
        return current
    try:
        return aiida.load_profile(name, allow_switch=True)
    except Exception as exc:  # ProfileConfigurationError, MissingConfigurationError, ...
        hint = "set one with `verdi profile set-default`" if name is None else "see `verdi profile list`"
        raise LookupError(f"cannot load AiiDA profile {name or '(default)'}: {exc}; {hint}") from exc


def load(node, links=(), profile=None):
    """The node with PK/UUID ``node``, after following ``links`` (output, called-process or
    input link labels; nested namespaces as ``a/b`` or ``a__b``)."""
    load_profile(profile)
    from aiida import orm

    try:
        found = orm.load_node(node)
    except Exception as exc:  # NotExistent, MultipleObjectsError
        raise LookupError(f"node {node}: {exc}") from exc
    for label in links:
        found = follow(found, label)
    return found


def follow(node, label):
    label = label.replace("/", "__")
    for t in outgoing(node):
        if t.link_label == label:
            return t.node
    for child in node.called if is_process(node) else []:
        if call_label(child) == label:   # a step of a WorkChain / task of a WorkGraph
            return child
    for t in node.base.links.get_incoming().all():
        if t.link_label == label:
            return t.node
    names = sorted({t.link_label for t in outgoing(node)})
    raise LookupError(f"node {node.pk} has no output {label!r}" + (f"; outputs: {', '.join(names)}" if names else ""))


def is_process(node):
    from aiida import orm

    return isinstance(node, orm.ProcessNode)


def outgoing(node):
    from aiida.common.links import LinkType

    if is_process(node):
        return node.base.links.get_outgoing(link_type=(LinkType.CREATE, LinkType.RETURN)).all()
    return []


def call_label(process):
    from aiida.common.links import LinkType

    calls = process.base.links.get_incoming(link_type=(LinkType.CALL_CALC, LinkType.CALL_WORK)).all()
    return calls[0].link_label if calls else ""


def descendants(process):
    """Every process ``process`` called, depth first, in the order they were created."""
    out = []
    for child in sorted(process.called, key=lambda n: (n.ctime, n.pk)):
        out.append(child)
        out += descendants(child)
    return out


def _value(state):
    return getattr(state, "value", state)


def info(node):
    out = {"pk": node.pk, "uuid": node.uuid, "node_type": node.node_type, "label": node.label}
    if is_process(node):
        out.update(process_label=node.process_label, process_state=_value(node.process_state),
                   exit_status=node.exit_status)
    return out


def scalars(node):
    """Numbers from the ``Dict``/``Float``/``Int`` outputs of a process, flat."""
    from aiida import orm

    out = {}
    for t in outgoing(node):
        if isinstance(t.node, orm.Dict):
            for key, value in t.node.get_dict().items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    out[key] = value
        elif isinstance(t.node, (orm.Float, orm.Int)):
            out[t.link_label] = t.node.value
    return out


def _of_type(node, name):
    from aiida import orm

    return isinstance(node, getattr(orm, name))


def is_phonopy(node):
    t = node.node_type
    return "phonopy" in t and ("PhonopyData" in t or "ForceConstantsData" in t)


def is_phonon_bands(bands):
    units = (bands.base.attributes.get("units", "") or "").lower()
    return units in ("thz", "cm-1", "cm^-1", "mev") or "phonon" in (bands.label or "").lower()


# ----------------------------------------------------------------------- views
def find_view(node, what=None):
    """``(view, items)``: the first of :data:`VIEWS` that ``node`` has, or ``what``.
    ``items`` are ``(label, node, source process or None)``. A trajectory is the node's own
    ``TrajectoryData`` output, else those of the processes it called, in call order."""
    from aiida import orm

    if what is not None and what not in VIEWS:
        raise ValueError(f"what= must be one of {', '.join(VIEWS)}")
    if not is_process(node):
        for view, cls in (("trajectory", "TrajectoryData"), ("structures", "StructureData"), ("bands", "BandsData")):
            if isinstance(node, getattr(orm, cls)):
                if view == "bands" and is_phonon_bands(node):
                    view = "phonons"
                if what in (None, view):
                    return view, [("", node, None)]
        if is_phonopy(node) and what in (None, "phonons"):
            return "phonons", [("", node, None)]
        raise ValueError(f"node {node.pk} is a {type(node).__name__}; ewald-aiida opens structures, "
                         "trajectories, bands, phonopy data and the processes that made them")
    procs = [node] + descendants(node)

    def outputs(proc, cls):
        return [(t.link_label, t.node, proc) for t in outgoing(proc) if _of_type(t.node, cls)]

    for view in VIEWS if what is None else (what,):
        if view == "trajectory":
            items = outputs(node, "TrajectoryData") or [i for p in procs[1:] for i in outputs(p, "TrajectoryData")]
        elif view == "phonons":
            items = [(t.link_label, t.node, p) for p in procs for t in outgoing(p) if is_phonopy(t.node)]
        elif view == "bands":
            items = [i for p in procs for i in outputs(p, "BandsData") if not is_phonon_bands(i[1])][-1:]
        elif view == "structures":
            items = outputs(node, "StructureData") or [i for p in procs[1:] for i in outputs(p, "StructureData")]
        else:
            items = [(t.link_label, t.node, node) for t in node.base.links.get_incoming().all()
                     if isinstance(t.node, orm.StructureData)][:1]
        items = _unique(items)
        if items:
            return view, items
    raise LookupError(f"process {node.pk} ({node.process_label}) has no "
                      f"{what or 'structure, trajectory, bands or phonon'} output")


def _unique(items):
    seen, out = set(), []
    for label, n, src in items:
        if n.pk not in seen:
            seen.add(n.pk)
            out.append((label, n, src))
    return out


def structure_of(node):
    """The structure a bands/phonon result belongs to: an output or input of its process,
    or of the processes that called it."""
    from aiida import orm

    proc = node if is_process(node) else node.creator
    while proc is not None:
        for t in list(outgoing(proc)) + proc.base.links.get_incoming().all():
            if isinstance(t.node, orm.StructureData):
                return t.node
        proc = proc.caller
    return None


# ----------------------------------------------------------------------- items to arrays
def _symbol(kind):
    if not kind.is_alloy and not kind.has_vacancies:
        return kind.symbol
    return kind.symbols[int(np.argmax(kind.weights))]


def structure_item(s, prefix, arrays):
    kinds = {k.name: k for k in s.kinds}
    arrays[prefix + "cell"] = np.array(s.cell, float)
    arrays[prefix + "positions"] = np.array([site.position for site in s.sites], float).reshape(-1, 3)
    return {"symbols": [_symbol(kinds[site.kind_name]) for site in s.sites],
            "kinds": [site.kind_name for site in s.sites], "pbc": [bool(p) for p in s.pbc]}


def trajectory_item(t, prefix, arrays):
    names = set(t.get_arraynames())
    pos = t.get_positions()
    arrays[prefix + "positions"] = pos
    if "cells" in names:
        arrays[prefix + "cells"] = t.get_cells()
    arrays[prefix + "steps"] = t.get_stepids() if "steps" in names else np.arange(len(pos))
    if "times" in names:
        arrays[prefix + "times"] = t.get_times()
    pbc = t.base.attributes.get("pbc", None)
    per_atom, per_step = {}, []
    for name in sorted(names - _TRAJ_ARRAYS):
        a = t.get_array(name)
        if a.ndim >= 2 and a.shape[:2] == pos.shape[:2]:
            per_atom[name] = PER_ATOM.get(name.lower(), name)
            arrays[prefix + "pa." + name] = a
        elif a.ndim == 1 and len(a) == len(pos):
            per_step.append(name)
            arrays[prefix + "ps." + name] = a
    return {"symbols": list(t.symbols), "pbc": None if pbc is None else [bool(p) for p in pbc],
            "per_atom": per_atom, "per_step": per_step}


def bands_item(b, prefix, arrays, source, extra):
    arrays[prefix + "bands"] = np.asarray(b.get_bands(), float)
    arrays[prefix + "kpoints"] = np.asarray(b.get_kpoints(), float)
    try:
        arrays[prefix + "kcart"] = np.asarray(b.get_kpoints(cartesian=True), float)
    except Exception:  # no cell on the node
        pass
    if "occupations" in b.get_arraynames():
        arrays[prefix + "occupations"] = np.asarray(b.get_array("occupations"), float)
    efermi = extra.get("fermi_energy")
    if efermi is None and source is not None:
        efermi = scalars(source).get("fermi_energy")
    out = {"labels": [[int(i), str(l)] for i, l in (b.labels or [])], "efermi": efermi,
           "units": b.base.attributes.get("units", None)}
    structure = structure_of(source or b)
    if structure is not None:
        out["structure"] = structure_item(structure, prefix + "s.", arrays)
    return out


def phonon_item(node, data, source):
    """aiida-phonopy force constants as a phonopy params YAML text, and the band path of the
    workflow's ``phonon_bands`` output (or None: seekpath)."""
    import os
    import tempfile

    top = node if is_process(node) else source
    phonon = phonopy_instance(data, top)
    fd, tmp = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    try:
        phonon.save(tmp, settings={"force_constants": True})
        with open(tmp, encoding="utf-8") as fh:
            text = fh.read()
    finally:
        os.remove(tmp)
    out = {"phonopy_yaml": text, "band_path": None, "band_labels": None}
    bands = phonon_bands(top)
    if bands is not None:
        out["band_path"], out["band_labels"] = band_path(bands)
    return out


def phonopy_instance(data, source=None):
    """``phonopy.Phonopy`` with force constants: from a ``ForceConstantsData``, a
    ``PhonopyData`` plus a ``ForceConstantsData`` its workflow made, or the forces it holds."""
    phonon = data.get_phonopy_instance()
    if phonon.force_constants is not None:
        return phonon
    for proc in ([source] + descendants(source)) if source is not None else []:
        for t in outgoing(proc):
            if "ForceConstantsData" in t.node.node_type:
                phonon.force_constants = t.node.get_phonopy_instance().force_constants
                return phonon
    forces = getattr(data, "forces", None)
    if forces is not None:
        phonon.forces = forces
        phonon.produce_force_constants()
        return phonon
    raise LookupError(f"node {data.pk} has no force constants or forces")


def phonon_bands(source):
    from aiida import orm

    if source is None or not is_process(source):
        return None
    for proc in [source] + descendants(source):
        for t in outgoing(proc):
            if isinstance(t.node, orm.BandsData) and is_phonon_bands(t.node):
                return t.node
    return None


def band_path(bands):
    """``(paths, labels)`` for phonopy from a ``BandsData``: paths of end points, connected
    within a path; two labels on neighbouring k-points mark a jump between paths."""
    k = np.asarray(bands.get_kpoints(), float)
    marks = sorted(dict(bands.labels or []).items())
    spans = [(i0, i1, l0, l1) for (i0, l0), (i1, l1) in zip(marks, marks[1:]) if i1 > i0 + 1]
    if not spans:
        return None, None
    paths, labels = [], []
    for j, (i0, i1, l0, l1) in enumerate(spans):
        if j == 0 or spans[j - 1][1] != i0:
            paths.append([k[i0].tolist()])
            labels.append(l0)
        paths[-1].append(k[i1].tolist())
        labels.append(l1)
    return paths, labels


# ----------------------------------------------------------------------- bundle
def bundle(node, links=(), what=None, profile=None):
    """``(meta, arrays)`` for node ``node`` (PK or UUID) after ``links``; see the module docstring."""
    top = load(node, links, profile)
    view, items = find_view(top, what)
    extra = scalars(top) if is_process(top) else {}
    arrays, entries = {}, []
    for k, (label, n, src) in enumerate(items):
        prefix = f"{k}."
        entry = {"label": label, "pk": n.pk, "uuid": n.uuid, "type": type(n).__name__,
                 "calc_pk": None if src is None or src.pk == top.pk else src.pk}
        if view == "trajectory":
            entry.update(trajectory_item(n, prefix, arrays))
            if src is not None and src.pk != top.pk:
                entry["scalars"] = scalars(src)
        elif view in ("structures", "input"):
            entry.update(structure_item(n, prefix, arrays))
        elif view == "bands":
            entry.update(bands_item(n, prefix, arrays, src, extra))
        else:
            entry.update(phonon_item(top, n, src))
        entries.append(entry)
    if view == "phonons":
        entries = entries[-1:]
    import aiida

    meta = {"format": 1, "node": info(top), "view": view, "scalars": extra, "items": entries,
            "profile": aiida.get_profile().name}
    return meta, arrays


def to_npz(meta, arrays) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, __meta__=np.frombuffer(json.dumps(meta).encode(), np.uint8), **arrays)
    return buf.getvalue()


def from_npz(blob: bytes):
    with np.load(io.BytesIO(blob), allow_pickle=False) as z:
        meta = json.loads(bytes(z["__meta__"]).decode())
        arrays = {k: z[k] for k in z.files if k != "__meta__"}
    return meta, arrays


# ----------------------------------------------------------------------- browsing
def _line(node, label=""):
    from aiida import orm

    name = node.process_label if is_process(node) else type(node).__name__
    state = ""
    if is_process(node):
        state = f" [{_value(node.process_state) or '?'}" + (
            f", exit {node.exit_status}]" if node.exit_status is not None else "]")
    extra = ""
    if isinstance(node, orm.StructureData):
        extra = f" {node.get_formula()}"
    elif isinstance(node, orm.TrajectoryData):
        extra = f" {node.numsteps} steps"
    return (f"{label}: " if label else "") + f"{name} <{node.pk}>{extra}{state}" + (f" '{node.label}'" if node.label else "")


def tree(node, profile=None, depth=4, links=()):
    """Text tree of a process: the processes it called and their outputs, with PKs."""
    top = load(node, links, profile)
    lines = [_line(top)]
    try:
        view, _ = find_view(top)
        lines[0] += f"  -> opens {view}"
    except (LookupError, ValueError):
        pass

    def walk(proc, prefix, level):
        kids = [(t.link_label, t.node, False) for t in outgoing(proc)]
        if level < depth:
            kids += [(call_label(c), c, True) for c in sorted(proc.called, key=lambda n: (n.ctime, n.pk))]
        for i, (label, child, is_proc) in enumerate(kids):
            last = i == len(kids) - 1
            lines.append(prefix + ("└─ " if last else "├─ ") + _line(child, label))
            if is_proc:
                walk(child, prefix + ("   " if last else "│  "), level + 1)

    if is_process(top):
        walk(top, "", 1)
    return "\n".join(lines)


def find(process_label=None, profile=None, limit=20, finished_ok=None):
    """Recent processes, newest first, as dicts (pk, uuid, process_label, state, exit_status,
    ctime, label)."""
    load_profile(profile)
    from aiida import orm

    filters = {}
    if process_label:
        filters["attributes.process_label"] = {"like": process_label} if "%" in process_label else process_label
    qb = orm.QueryBuilder().append(orm.ProcessNode, filters=filters, tag="p")
    qb.order_by({"p": {"ctime": "desc"}}).limit(limit * 4 if finished_ok is not None else limit)
    out = []
    for (n,) in qb.iterall():
        if finished_ok is not None and bool(n.is_finished_ok) != finished_ok:
            continue
        out.append({"pk": n.pk, "uuid": n.uuid, "process_label": n.process_label,
                    "state": _value(n.process_state), "exit_status": n.exit_status,
                    "ctime": n.ctime.isoformat(), "label": n.label})
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------------- command line
def _node_arg(text):
    return int(text) if text.isdigit() else text


def main(argv=None):
    import argparse

    p = argparse.ArgumentParser(prog="ewald-aiida-export")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bundle")
    b.add_argument("--profile")
    b.add_argument("--what")
    b.add_argument("node")
    b.add_argument("links", nargs="*")
    t = sub.add_parser("tree")
    t.add_argument("--profile")
    t.add_argument("--depth", type=int, default=4)
    t.add_argument("node")
    t.add_argument("links", nargs="*")
    f = sub.add_parser("find")
    f.add_argument("--profile")
    f.add_argument("--process")
    f.add_argument("--limit", type=int, default=20)
    f.add_argument("--ok", action="store_true")
    args = p.parse_args(argv)
    out = sys.stdout.buffer
    if args.command == "bundle":
        out.write(to_npz(*bundle(_node_arg(args.node), args.links, args.what, args.profile)))
    elif args.command == "tree":
        out.write(tree(_node_arg(args.node), args.profile, args.depth, args.links).encode())
    else:
        out.write(json.dumps(find(args.process, args.profile, args.limit, True if args.ok else None)).encode())
    out.flush()


ERROR = b"EWALD-AIIDA-ERROR "


def cli(argv=None):
    """:func:`main`, with a failure written to stdout as ``EWALD-AIIDA-ERROR <type>: <message>``
    and exit status 2, so the caller over SSH can show it."""
    try:
        main(argv)
    except Exception as exc:  # report, do not dump a traceback into the npz stream
        sys.stdout.buffer.write(ERROR + f"{type(exc).__name__}: {exc}".encode())
        sys.stdout.buffer.flush()
        sys.exit(2)


if __name__ == "__main__":
    cli()
