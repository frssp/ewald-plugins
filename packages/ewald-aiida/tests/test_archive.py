"""AiiDA archives as read-only profiles, and step shapes read from the inputs.

A small VASP-like WorkGraph (a bulk cell relaxation and a slab static with a planar average,
each a VaspWorkChain around one VaspCalculation) is stored in the test profile, exported with
``create_archive`` and opened in a fresh Python: loading an archive profile switches AiiDA
away from the in-memory test profile, which would empty it for the other tests.
"""
import io
import json
import os
import subprocess
import sys
import textwrap

import numpy as np
import pytest

from ewald_aiida import shape

pytest.importorskip("aiida")

VASPRUN = b"<?xml version='1.0'?><modeling><generator/></modeling>\n"
PLANAR = json.dumps({"z": [0.0, 1.0], "v": [0.0, 4.2]}).encode()


def _vasp_step(orm, wg, computer, name, structure, incar, kpoints, files):
    from aiida.common.links import LinkType

    wc = orm.WorkChainNode()
    wc.set_process_label("VaspWorkChain")
    wc.set_process_state("finished")
    wc.set_exit_status(0)
    wc.base.links.add_incoming(wg, LinkType.CALL_WORK, name)
    wc.store()
    params = orm.Dict(incar).store()
    calc = orm.CalcJobNode(computer=computer, process_type="aiida.calculations:vasp.vasp")
    calc.set_process_label("VaspCalculation")
    calc.set_process_state("finished")
    calc.set_exit_status(0)
    calc.set_option("resources", {"num_machines": 1})
    for label, node in (("structure", structure), ("parameters", params), ("kpoints", kpoints)):
        calc.base.links.add_incoming(node, LinkType.INPUT_CALC, label)
    calc.base.links.add_incoming(wc, LinkType.CALL_CALC, "iteration_01")
    calc.store()
    retrieved = orm.FolderData()
    for fname, data in files.items():
        retrieved.base.repository.put_object_from_filelike(io.BytesIO(data), fname)
    retrieved.base.links.add_incoming(calc, LinkType.CREATE, "retrieved")
    retrieved.store()
    for node in (calc, wc):
        node.seal()
    return calc


@pytest.fixture(scope="module")
def vasp_wg(graph):
    from aiida import orm
    from aiida.common.links import LinkType

    computer = orm.Computer(label="archive-test", hostname="localhost", transport_type="core.local",
                            scheduler_type="core.direct").store()
    bulk = orm.StructureData(cell=np.eye(3) * 4.0)
    bulk.append_atom(position=(0, 0, 0), symbols="Pt")
    bulk.store()
    slab = orm.StructureData(cell=np.diag([4.0, 4.0, 24.0]))
    for z in (0.0, 2.0, 4.0):
        slab.append_atom(position=(0, 0, z), symbols="Pt")
    slab.store()
    mesh = orm.KpointsData()
    mesh.set_kpoints_mesh([8, 8, 1])
    mesh.store()
    wg = orm.WorkChainNode()
    wg.set_process_label("WorkGraph<vasp_workfunction>")
    wg.set_process_state("finished")
    wg.set_exit_status(0)
    wg.base.links.add_incoming(bulk, LinkType.INPUT_WORK, "structure")
    wg.store()
    wg.base.extras.set("sim_agent_template", "vasp_workfunction")
    relax = _vasp_step(orm, wg, computer, "bulk_relax", bulk, {"IBRION": 2, "NSW": 50, "ISIF": 3, "ENCUT": 520},
                       mesh, {"vasprun.xml": VASPRUN})
    static = _vasp_step(orm, wg, computer, "slab_111_t1_static", slab,
                        {"incar": {"NSW": 0, "LVHAR": True, "ENCUT": 520, "NELECT": 30}}, mesh,
                        {"vasprun.xml": VASPRUN, "locpot_planar_avg.json": PLANAR})
    wg.seal()
    return {"wg": wg, "relax": relax, "static": static}


def test_kinds_from_incar():
    assert shape.kind({"parameters": {"IBRION": 0, "NSW": 1000, "ENCUT": 400}}) == "md"
    assert shape.kind({"parameters": {"IBRION": 6, "ENCUT": 400}}) == "phonon"
    assert shape.kind({"parameters": {"IBRION": 2, "NSW": 99, "ISIF": 3}}) == "relax"
    assert shape.kind({"parameters": {"ICHARG": 11}, "kpoints": {"path": 120}}) == "bands"
    assert shape.kind({"parameters": {"ICHARG": 11, "LORBIT": 11}, "kpoints": {"mesh": [9, 9, 9]}}) == "dos"
    assert shape.kind({"parameters": {"nsw": 0, "encut": 400}}) == "static"
    assert shape.kind({"parameters": {"ecutwfc": 40}}) == ""     # not VASP: no guess
    assert shape.kind({}) == ""
    assert shape.flags({"parameters": {"IBRION": 2, "NSW": 9, "ISIF": 3}}) == ["cell_relax"]
    assert shape.flags({"parameters": {"LVHAR": ".TRUE."}, "structure": {"vacuum_axis": 2}}) == ["slab", "potential"]


def test_steps_carry_inputs_files_and_shape(vasp_wg):
    from ewald_aiida import export
    from ewald_aiida.source import workflow

    d = export.describe(vasp_wg["wg"].pk)
    wf = workflow(d, f"aiida:{vasp_wg['wg'].pk}")
    steps = {s.name: s for _, s in wf.walk()}
    relax, static = steps["bulk_relax"], steps["slab_111_t1_static"]
    assert relax.shape["kind"] == "relax" and relax.shape["flags"] == ["cell_relax"]
    assert static.shape == {"kind": "static", "flags": ["slab", "potential", "charged"], "formula": "Pt3",
                            "sites": 3, "volume": pytest.approx(384.0)}
    assert static.files == ["locpot_planar_avg.json", "vasprun.xml"]
    assert static.inputs["kpoints"] == {"mesh": [8, 8, 1]}
    assert static.inputs["parameters"]["NELECT"] == 30        # unwrapped from "incar"
    assert static.runs == 1 and static.calc_id == str(vasp_wg["static"].pk)
    assert static.inputs["structure"]["extras"] == {}
    assert wf.extras["sim_agent_template"] == "vasp_workfunction"


OPEN = textwrap.dedent("""
    import json, sys
    import ewald_aiida
    from ewald import load
    wf = ewald_aiida.open_archive(sys.argv[1])
    steps = {s.name: s for _, s in wf.walk()}
    static = steps["slab_111_t1_static"]
    profile = wf.path.split(":", 1)[1].split("/")[0]
    path = ewald_aiida.retrieved_file(profile, static.id, "locpot_planar_avg.json")
    print(json.dumps({"path": wf.path, "kind": wf.kind, "steps": sorted(steps),
                      "shape": static.shape, "planar": open(path).read(),
                      "structure": load(wf.path, what="input").compute(0).count}))
""")


def _run(script, *args, env):
    out = subprocess.run([sys.executable, "-c", script, *args], check=False, capture_output=True, text=True, env=env,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_archive_opens_in_a_fresh_python_and_is_cached(vasp_wg, tmp_path):
    from aiida.tools.archive import create_archive

    archive = tmp_path / "wf.aiida"
    create_archive([vasp_wg["wg"]], filename=archive)
    env = {**os.environ, "EWALD_CACHE_DIR": str(tmp_path / "cache"), "AIIDA_PATH": str(tmp_path / "aiida")}
    first = _run(OPEN, str(archive), env=env)
    assert first["path"].startswith("aiida:archive-") and first["kind"] == "WorkGraph<vasp_workfunction>"
    assert {"bulk_relax", "slab_111_t1_static"} <= set(first["steps"])
    assert first["shape"]["kind"] == "static" and "potential" in first["shape"]["flags"]
    assert first["planar"] == PLANAR.decode()
    profile = first["path"].split(":", 1)[1].split("/")[0]
    folder = tmp_path / "cache" / "remote" / "aiida-archives" / profile
    assert (folder / ".ewald-ready").exists()

    again = _run(OPEN, str(archive), env=env)       # the extraction is reused
    assert again == first
    reopen = textwrap.dedent("""
        import json, sys
        from ewald import load
        print(json.dumps({"count": load(sys.argv[1], what="input").compute(0).count}))
    """)
    assert _run(reopen, first["path"], env=env)["count"] == first["structure"]  # a later session


def test_not_an_archive(tmp_path):
    from ewald_aiida import archives

    bad = tmp_path / "x.aiida"
    bad.write_text("no zip", encoding="utf-8")
    with pytest.raises(ValueError, match="not an AiiDA archive"):
        archives.open_archive(bad)
    with pytest.raises(LookupError, match="open its .aiida file again"):
        archives.resolve("archive-0000000000000000")
