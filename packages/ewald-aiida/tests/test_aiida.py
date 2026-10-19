import numpy as np
import pytest

import ewald_aiida
from ewald import load, plugins
from ewald_aiida import parse
from ewald_aiida.uri import AiidaURI


def _count():
    from aiida import orm

    return orm.QueryBuilder().append(orm.Node).count()


@pytest.mark.parametrize("text, uri", [
    ("aiida:1234", AiidaURI(1234)),
    ("aiida:prof/1234", AiidaURI(1234, (), "prof")),
    ("aiida:3F9C2E1A", AiidaURI("3f9c2e1a")),
    ("aiida:1234/relax/output_structure", AiidaURI(1234, ("relax", "output_structure"))),
    ("aiida:my-prof/8/output_band", AiidaURI(8, ("output_band",), "my-prof")),
    ("aiida://nurion/1234", AiidaURI(1234, host="nurion")),
    ("aiida://sim-agent@nurion:2222/prof/3f9c/relax", AiidaURI("3f9c", ("relax",), "prof", "nurion", "sim-agent", 2222)),
])
def test_parse(text, uri):
    assert parse(text) == uri
    assert parse(str(uri)) == uri


@pytest.mark.parametrize("bad", ["aiida:", "aiida:prof", "aiida:prof/x/1", "POSCAR", "aiida://host", "aiida://a@/1"])
def test_parse_errors(bad):
    with pytest.raises(ValueError):
        parse(bad)


def test_reader_is_registered_for_the_scheme():
    assert plugins.scheme_reader("aiida:1").name == "aiida"
    assert any(p["id"] == "aiida" and p["state"] == "loaded" for p in plugins.status()["plugins"])


def test_structure_by_pk_and_uuid(graph):
    si = graph["input"]
    for ident in (si.pk, si.uuid, si.uuid[:8]):
        data = load(f"aiida:{ident}").compute(0)
        assert list(data.types) == ["Si", "Si"]
        np.testing.assert_allclose(data.positions[1], [5.43 / 4] * 3)
        np.testing.assert_allclose(data.cell.matrix, np.eye(3) * 5.43)
        assert data.attributes["AiiDA"]["uuid"] == si.uuid


def test_workflow_opens_the_trajectories_of_its_calculations(graph):
    before = _count()
    pipe = load(f"aiida:{graph['relax'].pk}")
    assert pipe.num_frames == 5                                  # 3 + 2 steps over the restart
    first, last = pipe.compute(0), pipe.compute(4)
    assert [first.attributes["Timestep"], last.attributes["Timestep"]] == [0, 4]
    np.testing.assert_allclose(last.particles["Force"], 0.1 / 4)
    assert last.attributes["energy"] == pytest.approx(-10.4)    # per-step array of the trajectory
    info = last.attributes["AiiDA"]
    assert info["pk"] == graph["relax"].pk and info["view"] == "trajectory"
    assert info["calc_pk"] == graph["calc2"].pk and info["output_pk"] == graph["traj2"].pk
    assert info["process_label"] == "PwRelaxWorkChain" and info["exit_status"] == 0
    assert first.attributes["fermi_energy"] == 6.1               # Dict outputs of the workflow
    assert _count() == before                                    # read-only


def test_views_and_links(graph):
    relax = graph["relax"].pk
    structures = load(f"aiida:{relax}", what="structures")
    assert structures.num_frames == 1                           # the workflow's own output
    assert structures.compute(0).attributes["AiiDA"]["output_pk"] == graph["final"].pk
    assert load(f"aiida:{relax}", what="input").compute(0).attributes["AiiDA"]["output_pk"] == graph["input"].pk
    linked = load(f"aiida:{relax}/iteration_01/output_structure").compute(0)
    assert linked.attributes["AiiDA"]["pk"] != graph["final"].pk
    np.testing.assert_allclose(linked.positions[1, 0], 5.43 / 4 + 0.01)
    with pytest.raises(LookupError, match="output_structure"):
        load(f"aiida:{relax}/nothing")
    with pytest.raises(LookupError, match="no bands"):
        load(f"aiida:{relax}", what="bands")


def test_electronic_bands(graph):
    data = load(f"aiida:{graph['bands_calc'].pk}").compute(0)
    es = data.attributes["Electronic Structure"]
    assert es.eigenvalues.shape == (1, 13, 8) and data.attributes["Fermi Energy"] == 6.1
    assert [t[1] for t in es.ticks] == ["Γ", "X", "W", "K", "Γ"]
    assert es.breaks == [8]                                      # W|K is a jump in the path
    assert es.distances[8] == es.distances[7]
    assert "Bands" in data.tables and data.count == 2


def test_phonopy_workflow_gives_phonon_modes(graph):
    pytest.importorskip("ewald_phonopy")
    before = _count()
    pipe = load(f"aiida:{graph['phonon_wf'].pk}", frames=8)
    assert pipe.num_frames == 8
    data = pipe.compute(0)
    modes = data.attributes["Phonon Modes"]
    freqs = np.asarray(modes.frequencies)
    assert freqs.shape[-1] == 3 and abs(freqs[0]).min() < 0.05   # acoustic modes at Gamma
    assert freqs.max() == pytest.approx(7.3, abs=1.0)            # Cu EMT, THz
    assert data.attributes["AiiDA"]["view"] == "phonons"
    np.testing.assert_allclose(modes.qpoints[-1], [0, 0, 0])     # the path of the phonon_bands output
    assert [t[1] for t in modes.ticks] == ["GAMMA", "X", "W|K", "GAMMA"]
    assert _count() == before


def test_tree_and_find(graph):
    text = ewald_aiida.tree(graph["relax"].pk)
    assert f"PwRelaxWorkChain <{graph['relax'].pk}>" in text and "-> opens trajectory" in text
    assert f"iteration_02: PwCalculation <{graph['calc2'].pk}>" in text
    assert "output_trajectory: TrajectoryData" in text and "2 steps" in text
    rows = ewald_aiida.find("Pw%")
    assert {r["pk"] for r in rows} >= {graph["relax"].pk, graph["calc1"].pk}
    assert ewald_aiida.find("PhonopyWorkChain")[0]["uri"] == f"aiida:{graph['phonon_wf'].pk}"


def test_session_keeps_the_aiida_string(graph, tmp_path):
    from ewald.session import load_session, save_session

    pipe = load(f"aiida:{graph['relax'].pk}", what="structures")
    save_session(tmp_path / "s.ewald", pipe)
    again = load_session(tmp_path / "s.ewald").pipeline
    assert again.source.path == f"aiida:{graph['relax'].pk}" and again.num_frames == 1


def test_unknown_profile_is_a_clear_error():
    with pytest.raises(LookupError, match="no-such-profile"):
        load("aiida:no-such-profile/1")


def test_kinds_are_kept(graph):
    from aiida import orm

    s = orm.StructureData(cell=np.eye(3) * 3)
    s.append_atom(position=(0, 0, 0), symbols="Fe", name="Fe1")
    s.append_atom(position=(1.5, 1.5, 1.5), symbols="Fe", name="Fe2")
    s.store()
    data = load(f"aiida:{s.uuid}").compute(0)
    assert list(data.types) == ["Fe", "Fe"] and list(data.particles["Kind"]) == ["Fe1", "Fe2"]


# ----------------------------------------------------------------------- remote
class FakeHost:
    """Runs the exporter command the way a remote shell would, in this process (the profile
    is the test profile), and records the commands."""

    def __init__(self, verdi_python="/opt/aiida/bin/python"):
        self.commands = []
        self.verdi_python = verdi_python

    def run(self, command, timeout=600):
        import contextlib
        import io
        import shlex
        import sys

        self.commands.append(command)
        if command.startswith("bash -lc"):
            return 0, f"#!{self.verdi_python}\n".encode()
        python, flag, code, *args = shlex.split(command)
        assert flag == "-c" and python == self.verdi_python
        out = io.BytesIO()

        class Stdout:
            buffer = out

        old = sys.argv
        sys.argv = ["-c", *args]
        status = 0
        try:
            with contextlib.redirect_stdout(Stdout()):
                exec(code, {"__name__": "__main__"})
        except SystemExit as exc:
            status = exc.code
        finally:
            sys.argv = old
        return status, out.getvalue()


@pytest.fixture
def fake_host(monkeypatch, tmp_path):
    from ewald_aiida import transport

    host = FakeHost()
    monkeypatch.setattr(transport, "_connection", lambda uri: host)
    monkeypatch.setattr(transport, "_PYTHON", {})
    monkeypatch.setenv("EWALD_CACHE_DIR", str(tmp_path / "cache"))
    return host


def test_remote_workflow_over_ssh(graph, fake_host):
    relax = graph["relax"]
    local = load(f"aiida:{relax.pk}")
    pipe = load(f"aiida://sim-agent@nurion/{relax.pk}")
    assert pipe.num_frames == local.num_frames == 5
    a, b = pipe.compute(4), local.compute(4)
    np.testing.assert_allclose(a.positions, b.positions)
    np.testing.assert_allclose(a.particles["Force"], b.particles["Force"])
    assert a.attributes["AiiDA"]["host"] == "nurion" and a.attributes["AiiDA"]["calc_pk"] == graph["calc2"].pk
    assert a.attributes["fermi_energy"] == 6.1
    assert fake_host.commands[0].startswith("bash -lc")          # found verdi's python once
    assert "bundle" in fake_host.commands[1] and "/opt/aiida/bin/python" in fake_host.commands[1]
    bands = load(f"aiida://nurion/{graph['bands_calc'].pk}").compute(0)
    assert bands.attributes["Electronic Structure"].eigenvalues.shape == (1, 13, 8)


def test_remote_phonons_structures_and_browsing(graph, fake_host):
    pytest.importorskip("ewald_phonopy")
    modes = load(f"aiida://nurion/{graph['phonon_wf'].pk}", frames=4).compute(0).attributes["Phonon Modes"]
    assert [t[1] for t in modes.ticks] == ["GAMMA", "X", "W|K", "GAMMA"]
    s = load(f"aiida://nurion/{graph['relax'].pk}/iteration_01/output_structure").compute(0)
    np.testing.assert_allclose(s.positions[1, 0], 5.43 / 4 + 0.01)
    assert "iteration_02: PwCalculation" in ewald_aiida.tree(f"aiida://nurion/{graph['relax'].pk}")
    rows = ewald_aiida.find("PhonopyWorkChain", host="nurion")
    assert rows[0]["uri"] == f"aiida://nurion/{graph['phonon_wf'].pk}"


def test_remote_errors_and_cache(graph, fake_host):
    with pytest.raises(LookupError, match="on nurion: LookupError: node 999999"):
        load("aiida://nurion/999999")
    uuid = graph["final"].uuid
    load(f"aiida://nurion/{uuid}")
    n = len(fake_host.commands)
    assert load(f"aiida://nurion/{uuid}").compute(0).count == 2   # a full UUID is cached
    assert len(fake_host.commands) == n
    load(f"aiida://nurion/{graph['final'].pk}")
    load(f"aiida://nurion/{graph['final'].pk}")                   # a PK is asked again
    assert len(fake_host.commands) == n + 2


def test_exporter_runs_without_ewald():
    """The remote side gets only export.py (as the payload): it must compile on its own and
    import nothing of ewald."""
    import ast
    import base64
    import re
    import zlib

    from ewald_aiida import transport

    blob = re.search(r"b64decode\('([^']+)'\)", transport.payload())[1]
    tree = ast.parse(zlib.decompress(base64.b64decode(blob)))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}
    assert not any(isinstance(n, ast.ImportFrom) and n.level for n in ast.walk(tree))
    assert mods <= {"__future__", "aiida", "argparse", "io", "json", "numpy", "os", "sys", "tempfile"}
