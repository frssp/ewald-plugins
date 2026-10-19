"""Plumed from a session file or Claude refuses inputs that load code or reach outside their folder,
and the colvar table links frames to a free energy surface (ewald.linking)."""
import numpy as np
import pytest
from ase.build import bulk

from ewald import DataCollection, Pipeline, StaticSource, linking
from ewald import modifiers as mods
from ewald.session import modifier_from_dict
from ewald_plumed.modifiers import LoadColvar
from ewald_plumed.plumed import untrusted_input_problems


def test_session_plumed_with_load_or_kernel_is_disabled():
    entry = {"type": "Plumed", "module": "ewald_plumed.modifiers",
             "parameters": {"input": "LOAD FILE=/tmp/evil.so\nd: DISTANCE ATOMS=1,2\n"}}
    m, warning = modifier_from_dict(entry)
    assert not m.enabled and "LOAD" in warning
    entry["parameters"] = {"input": "d: DISTANCE ATOMS=1,2\n", "kernel": "/tmp/evil.so"}
    m, warning = modifier_from_dict(entry)
    assert not m.enabled and "kernel" in warning
    entry["parameters"] = {"input": "d: DISTANCE ATOMS=1,2\nPRINT ARG=d FILE=COLVAR\n"}
    m, warning = modifier_from_dict(entry)
    assert m.enabled and warning is None
    assert modifier_from_dict({**entry, "parameters": {"input": "LOAD FILE=x.so\n"}}, allow_code=True)[0].enabled


def test_session_from_before_the_move_still_loads():
    m, warning = modifier_from_dict({"type": "Plumed", "module": "ewald.modifiers.plumed",
                                     "parameters": {"input": "d: DISTANCE ATOMS=1,2\n"}})
    assert type(m).__module__ == "ewald_plumed.modifiers" and warning is None
    import ewald.plumed

    assert ewald.plumed.fes_from_hills is not None


def test_untrusted_plumed_input():
    assert untrusted_input_problems("d: DISTANCE ATOMS=1,2\nPRINT ARG=d FILE=COLVAR\n") == []
    problems = untrusted_input_problems("x: LOAD FILE=a.cpp\nPRINT ARG=d FILE=~/.bashrc\nREFERENCE=../../a.pdb\n")
    assert len(problems) == 3


def test_claude_tools_refuse_plumed_load():
    from ewald.llm.tools import Toolset

    ts = Toolset(Pipeline(StaticSource([DataCollection.from_ase(bulk("Cu"))])))
    r = ts.call("compute_plumed_cvs", {"input": "LOAD FILE=/tmp/evil.so\nd: DISTANCE ATOMS=1,2\n"})
    assert r.is_error and "LOAD" in str(r.content)


def test_fes_box_selects_frames_through_colvar(tmp_path):
    cu = DataCollection.from_ase(bulk("Cu", "fcc", a=3.615, cubic=True))
    colvar = tmp_path / "COLVAR"
    rows = [(0, 0.1, 0.1), (1, 0.9, 0.1), (2, 0.9, 0.9), (3, 0.15, 0.2), (4, 0.5, 0.5), (5, 0.5, 0.5)]
    colvar.write_text("#! FIELDS time d1 d2\n" + "".join(f"{t} {a} {b}\n" for t, a, b in rows))
    g = np.linspace(0, 1, 5)
    x, y = np.meshgrid(g, g)

    def fes(frame, data):
        data.tables["fes"] = {"d1": x.ravel(), "d2": y.ravel(), "Free Energy": (x + y).ravel()}

    # stride 2: frame k is COLVAR row 2k, so rows 1, 3 and 5 belong to no frame
    pipe = Pipeline(StaticSource([cu] * 3), [LoadColvar(str(colvar), stride=2), mods.PythonModifier(fes)])
    d = pipe.compute(0)
    L = linking.link_for(d, "fes")
    assert L == linking.Link("frames2d", "fes", "colvar")
    np.testing.assert_array_equal(linking.frame_rows(pipe, d, "colvar"), [0, 2, 4])
    assert linking.frames_in_box(pipe, d, L, 0, 0.3, 0, 0.3) == [0]
    assert linking.frames_in_box(pipe, d, L, 0.4, 1, 0.4, 1) == [1, 2]
