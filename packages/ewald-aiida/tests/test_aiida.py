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
])
def test_parse(text, uri):
    assert parse(text) == uri
    assert parse(str(uri)) == uri


@pytest.mark.parametrize("bad", ["aiida:", "aiida:prof", "aiida:prof/x/1", "POSCAR"])
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
    assert [t[1] for t in modes.ticks][:2] == ["GAMMA", "X"]       # (labels after a break: ewald-phonopy)
    assert _count() == before


def test_tree_and_find(graph):
    text = ewald_aiida.tree(graph["relax"].pk)
    assert f"PwRelaxWorkChain <{graph['relax'].pk}>" in text and "opens trajectory" in text
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
