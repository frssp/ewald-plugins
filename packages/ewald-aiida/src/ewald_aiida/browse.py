"""Browse the provenance graph: :func:`tree` and :func:`find`."""
from __future__ import annotations

from . import nodes
from .uri import load_profile


def _line(node, label: str = "") -> str:
    name = node.process_label if nodes._is_process(node) else type(node).__name__
    state = ""
    if nodes._is_process(node):
        state = f" [{nodes._value(node.process_state) or '?'}"
        state += f", exit {node.exit_status}]" if node.exit_status is not None else "]"
    extra = ""
    from aiida import orm

    if isinstance(node, orm.StructureData):
        extra = f" {node.get_formula()}"
    elif isinstance(node, orm.TrajectoryData):
        extra = f" {node.numsteps} steps"
    head = f"{label}: " if label else ""
    return f"{head}{name} <{node.pk}>{extra}{state}" + (f" '{node.label}'" if node.label else "")


def tree(identifier, profile: str | None = None, depth: int = 4, outputs: bool = True) -> str:
    """Text tree of a process: the processes it called and their outputs, with PKs, and
    the ``aiida:`` string that opens the node and its default view."""
    node = nodes.load(str(identifier) if str(identifier).startswith("aiida:") else f"aiida:{identifier}", profile)
    lines = [_line(node)]
    try:
        view, _ = nodes.find_view(node)
        lines[0] += f"  -> load(\"aiida:{node.pk}\") opens {view}"
    except (LookupError, ValueError):
        pass

    def walk(proc, prefix, level):
        kids = []
        if outputs:
            kids += [(t.link_label, t.node, False) for t in nodes._outgoing(proc)]
        if level < depth:
            kids += [(nodes._call_label(c), c, True) for c in sorted(proc.called, key=lambda n: (n.ctime, n.pk))]
        for i, (label, child, is_proc) in enumerate(kids):
            last = i == len(kids) - 1
            lines.append(prefix + ("└─ " if last else "├─ ") + _line(child, label))
            if is_proc:
                walk(child, prefix + ("   " if last else "│  "), level + 1)

    if nodes._is_process(node):
        walk(node, "", 1)
    return "\n".join(lines)


def find(process_label: str | None = None, profile: str | None = None, limit: int = 20,
         finished_ok: bool | None = None) -> list[dict]:
    """Recent processes, newest first: ``[{"pk", "uuid", "process_label", "state", "exit_status",
    "ctime", "label", "uri"}]``. ``process_label`` matches exactly or with ``%`` wildcards."""
    load_profile(profile)
    from aiida import orm

    filters = {}
    if process_label:
        filters["attributes.process_label"] = {"like": process_label} if "%" in process_label else process_label
    qb = orm.QueryBuilder().append(orm.ProcessNode, filters=filters, tag="p")
    qb.order_by({"p": {"ctime": "desc"}}).limit(limit * 4 if finished_ok is not None else limit)
    out = []
    for (node,) in qb.iterall():
        if finished_ok is not None and bool(node.is_finished_ok) != finished_ok:
            continue
        out.append({"pk": node.pk, "uuid": node.uuid, "process_label": node.process_label,
                    "state": nodes._value(node.process_state), "exit_status": node.exit_status,
                    "ctime": node.ctime.isoformat(), "label": node.label,
                    "uri": f"aiida:{profile + '/' if profile else ''}{node.pk}"})
        if len(out) >= limit:
            break
    return out
