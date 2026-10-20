"""AiiDA as an EWALD workflow source (:mod:`ewald.workflow`): the whole workflows of a profile
(processes nobody called) newest first, each described as the processes it called, nested,
with their structures, trajectories and bands.

Where the profile is comes from the plugin's settings page (Edit › Plugin settings › AiiDA): a
host (empty: this machine), a profile (empty: the default one) and the Python that runs
``verdi`` there (empty: found from ``verdi``). EWALD builds the side bar, "open as one notebook"
and the AI tools from this; every path is an ``aiida:`` path the reader opens.
"""
from __future__ import annotations

import re

from ewald.plugin_api import (
    SettingsField,
    Workflow,
    WorkflowOutput,
    WorkflowPage,
    WorkflowStep,
)

from . import transport
from .uri import AiidaURI, parse

_RESTART = re.compile(r"^iteration_\d+$")
PAGE = 50


class AiidaSettings:
    """Where the AiiDA profile is: this machine, or another one over SSH."""

    title = "AiiDA"
    fields = (
        SettingsField("host", "Host", placeholder="empty: this machine",
                      help="[user@]host[:port], an ~/.ssh/config alias or a saved Remotes computer"),
        SettingsField("profile", "Profile", placeholder="empty: the default profile"),
        SettingsField("python", "Python on the host", placeholder="empty: the one that runs verdi",
                      help="Only for a host: the Python of the AiiDA environment, e.g. /opt/aiida/bin/python"),
    )


def settings() -> dict:
    try:
        from ewald.plugin_api import plugin_settings

        return plugin_settings("aiida")
    except KeyError:      # the settings page is switched off or not registered (tests)
        return {}


def _base(values: dict) -> AiidaURI | None:
    host = (values.get("host") or "").strip()
    return parse(f"aiida://{host}/0") if host else None


def _uri(node, links=(), profile=None, base: AiidaURI | None = None) -> str:
    if base is None:
        return str(AiidaURI(node, tuple(links), profile or None))
    return str(AiidaURI(node, tuple(links), profile or None, base.host, base.user, base.port))


class AiidaWorkflows:
    """The workflows of an AiiDA profile, on this machine or another (Settings › AiiDA)."""

    title = "AiiDA"
    schemes = ("aiida",)
    settings_page = "aiida"

    def __init__(self, values: dict | None = None):
        self.values = values

    def _values(self) -> dict:
        return self.values if self.values is not None else settings()

    def account(self) -> str:
        v = self._values()
        profile = v.get("profile") or "default profile"
        if v.get("host"):
            return f"{profile} on {v['host']}"
        try:
            import aiida  # noqa: F401 (only whether it is installed here)
        except ImportError:
            return ""     # nothing here: the side bar asks for a host
        return f"{profile} on this machine"

    def list(self, query: str | None = None, cursor: str | None = None) -> WorkflowPage:
        v = self._values()
        base = _base(v)
        found = transport.page(base, v.get("profile") or None, PAGE, query or None, int(cursor or 0),
                               v.get("python") or None)
        rows = [Workflow(r["process_label"] or "process", id=str(r["pk"]), path=_uri(r["pk"], (), v.get("profile"), base),
                         kind=r["process_label"] or "", state=r.get("state") or "", exit_status=r.get("exit_status"),
                         label=r.get("label") or "", description=r.get("description") or "", ctime=r.get("ctime") or "")
                for r in found["rows"]]
        return WorkflowPage(rows, next=None if found["next"] is None else str(found["next"]))

    def describe(self, ref: str) -> Workflow:
        v = self._values()
        text = str(ref)
        if text.lower().startswith("aiida:"):
            uri = parse(text)
        else:
            base = _base(v)
            uri = parse(_uri(int(text) if text.isdigit() else text, (), v.get("profile"), base))
        d = transport.describe(uri, None, python=v.get("python") or None)
        base = AiidaURI(0, (), None, uri.host, uri.user, uri.port) if uri.host else None
        return workflow(d, str(uri), uri.profile, base)


def _outputs(d: dict, path: str) -> list:
    out = []
    for o in d.get("outputs", []):
        note = o.get("formula") or (f"{o['steps']} steps" if o.get("steps") else "")
        kind = {"bands": "data", "phonons": "data"}.get(o["kind"], o["kind"])
        link = o["link"]
        out.append(WorkflowOutput(link or o["kind"], f"{path}/{link}" if link else path, kind=kind,
                                  note=note or ("phonons" if o["kind"] == "phonons" else "")))
    return out


def _state(d: dict) -> dict:
    return {"state": d.get("process_state") or "", "exit_status": d.get("exit_status")}


def _step(d: dict, path: str, profile, base) -> WorkflowStep:
    step = WorkflowStep(d.get("call_label") or d.get("process_label") or "step", id=str(d["pk"]),
                        work_dir=d.get("work_dir") or "", scalars=dict(d.get("scalars") or {}), **_state(d))
    _fill(step, d, path, profile, base)
    return step


def _fill(step, d: dict, path: str, profile, base):
    """``step`` (the process ``d``, opened by ``path``) gets its outputs and called processes;
    a process that only restarted one calculation (``iteration_01``, ``iteration_02``, ...) is
    one step with ``runs``, as AiiDA's restart workchains run it."""
    step.path = path if d.get("view") else ""
    step.outputs = _outputs(d, path)
    called = d.get("called") or []
    if called and all(_RESTART.match(c.get("call_label") or "") for c in called):
        last = called[-1]
        step.runs = len(called)
        step.work_dir = step.work_dir or last.get("work_dir") or ""
        step.scalars = {**(last.get("scalars") or {}), **step.scalars}
        if not step.outputs:
            step.outputs = _outputs(last, f"{path}/{last['call_label']}")
        return
    labels = [c.get("call_label") or "" for c in called]
    for c in called:
        label = c.get("call_label") or ""
        unique = label and label != "CALL" and labels.count(label) == 1
        child_path = f"{path}/{label}" if unique else _uri(c["pk"], (), profile, base)
        step.steps.append(_step(c, child_path, profile, base))


def workflow(d: dict, path: str, profile=None, base: AiidaURI | None = None) -> Workflow:
    """:func:`ewald_aiida.export.describe` output as a Workflow; ``path`` opens its top."""
    wf = Workflow(d.get("process_label") or d.get("node_type") or "node", id=str(d["pk"]), path=path,
                  kind=d.get("process_label") or "", label=d.get("label") or "",
                  description=d.get("description") or "", ctime=d.get("ctime") or "", complete=True,
                  scalars=dict(d.get("scalars") or {}), work_dir=d.get("work_dir") or "", **_state(d))
    _fill(wf, d, path, profile, base)
    wf.path = path
    formulas = [o.note for o in wf.outputs if o.kind == "structure" and o.note]
    wf.formula = formulas[-1] if formulas else ""
    return wf
