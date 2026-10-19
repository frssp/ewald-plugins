"""A throwaway AiiDA profile (in-memory SQLite, no RabbitMQ) holding a small provenance graph:
a relaxation WorkChain with two restarts, an electronic band structure and an aiida-phonopy
result. Nodes are stored by hand, as the real plugins would store them."""
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _ewald_config(tmp_path, monkeypatch):
    monkeypatch.setenv("EWALD_CONFIG_DIR", str(tmp_path / "ewald-config"))


def _structure(orm, a=5.43, shift=0.0):
    s = orm.StructureData(cell=np.eye(3) * a)
    s.append_atom(position=(0, 0, 0), symbols="Si")
    s.append_atom(position=(a / 4 + shift, a / 4, a / 4), symbols="Si")
    return s


def _process(orm, cls, label, state="finished", caller=None, call_label=None, inputs=()):
    from aiida.common.links import LinkType

    node = cls()
    node.set_process_label(label)
    node.set_process_state(state)
    node.set_exit_status(0)
    for link_label, data in inputs:
        link = LinkType.INPUT_CALC if isinstance(node, orm.CalculationNode) else LinkType.INPUT_WORK
        node.base.links.add_incoming(data, link, link_label)
    if caller is not None:
        link = LinkType.CALL_CALC if isinstance(node, orm.CalculationNode) else LinkType.CALL_WORK
        node.base.links.add_incoming(caller, link, call_label or label)
    return node.store()


def _create(calc, data, label):
    from aiida.common.links import LinkType

    data.base.links.add_incoming(calc, LinkType.CREATE, label)
    return data.store()


def _return(work, data, label):
    from aiida.common.links import LinkType

    data.base.links.add_incoming(work, LinkType.RETURN, label)


def _trajectory(orm, structure, steps, start):
    pos0 = np.array([s.position for s in structure.sites])
    pos = np.stack([pos0 + 0.01 * i for i in range(steps)])
    traj = orm.TrajectoryData()
    traj.set_trajectory(["Si", "Si"], pos, stepids=np.arange(start, start + steps),
                        cells=np.stack([structure.cell] * steps), pbc=[True, True, True])
    traj.set_array("forces", np.full((steps, 2, 3), 0.1) / (start + 1))
    traj.set_array("energy", -10.0 - 0.1 * np.arange(start, start + steps))
    return traj


def _phonopy(orm):
    """aiida-phonopy PhonopyData (Cu fcc, 2x2x2 supercell, EMT forces) and its force constants."""
    from aiida_phonopy.data import ForceConstantsData, PhonopyData, PreProcessData
    from ase.build import bulk
    from ase.calculators.emt import EMT

    cu = bulk("Cu", "fcc", a=3.61)
    structure = orm.StructureData(ase=cu)
    pre = PreProcessData(structure=structure, supercell_matrix=[[2, 0, 0], [0, 2, 0], [0, 0, 2]],
                         primitive_matrix="auto")
    pre.set_displacements()
    forces = []
    for sc in pre.get_supercells_with_displacements().values():
        atoms = sc.get_ase()
        atoms.calc = EMT()
        forces.append(atoms.get_forces())
    data = PhonopyData(preprocess_data=pre)
    data.set_forces(np.array(forces))
    phonon = data.get_phonopy_instance()
    phonon.produce_force_constants()
    fc = ForceConstantsData(structure=structure, supercell_matrix=[[2, 0, 0], [0, 2, 0], [0, 0, 2]],
                            primitive_matrix="auto")
    fc.set_force_constants(phonon.force_constants)
    return structure, data, fc


@pytest.fixture(scope="session")
def graph():
    """``{"relax", "calc1", "calc2", "final", "bands_calc", "bands", "phonon_wf", "phonopy_data", ...}``."""
    from aiida import load_profile, orm
    from aiida.storage.sqlite_temp import SqliteTempBackend

    load_profile(SqliteTempBackend.create_profile("ewald-aiida-test"), allow_switch=True)
    g = {}
    si = _structure(orm).store()
    g["input"] = si
    relax = _process(orm, orm.WorkChainNode, "PwRelaxWorkChain", inputs=[("structure", si)])
    g["relax"] = relax
    last = si
    for k, (steps, start) in enumerate(((3, 0), (2, 3))):
        calc = _process(orm, orm.CalcFunctionNode, "PwCalculation", caller=relax, call_label=f"iteration_{k + 1:02d}",
                        inputs=[("structure", last)])
        g[f"calc{k + 1}"] = calc
        g[f"traj{k + 1}"] = _create(calc, _trajectory(orm, last, steps, start), "output_trajectory")
        last = _create(calc, _structure(orm, shift=0.01 * (k + 1)), "output_structure")
        _create(calc, orm.Dict({"energy": -10.5 - k, "fermi_energy": 6.1, "code": "pw"}), "output_parameters")
    _return(relax, last, "output_structure")
    _return(relax, orm.Dict({"energy": -11.5, "fermi_energy": 6.1}).store(), "output_parameters")
    g["final"] = last

    bands_calc = _process(orm, orm.CalcFunctionNode, "PwCalculation", inputs=[("structure", si)])
    bands = orm.BandsData()
    bands.set_cell(si.cell, pbc=si.pbc)
    k = np.concatenate([np.linspace([0, 0, 0], [0.5, 0, 0.5], 6), np.linspace([0.5, 0, 0.5], [0.5, 0.25, 0.75], 3)[1:],
                        np.linspace([0.375, 0.375, 0.75], [0, 0, 0], 5)])
    bands.set_kpoints(k)
    e = np.stack([np.linspace(-6, -1, len(k)) + i for i in range(8)], axis=1)
    bands.set_bands(e, units="eV", occupations=(e < 6.1).astype(float) * 2)
    bands.labels = [(0, "GAMMA"), (5, "X"), (7, "W"), (8, "K"), (12, "GAMMA")]
    g["bands"] = _create(bands_calc, bands, "output_band")
    _create(bands_calc, orm.Dict({"fermi_energy": 6.1}), "output_parameters")
    g["bands_calc"] = bands_calc

    cu, data, fc = _phonopy(orm)
    cu.store()
    wf = _process(orm, orm.WorkChainNode, "PhonopyWorkChain", inputs=[("structure", cu)])
    g["phonon_wf"] = wf
    phcalc = _process(orm, orm.CalcFunctionNode, "generate_phonopy_data", caller=wf, inputs=[("structure", cu)])
    g["phonopy_data"] = _create(phcalc, data, "phonopy_data")
    _return(wf, g["phonopy_data"], "phonopy_data")
    g["phonon_fc_calc"] = fc_calc = _process(orm, orm.CalcFunctionNode, "get_force_constants", caller=wf,
                                             inputs=[("phonopy_data", g["phonopy_data"])])
    g["force_constants"] = _create(fc_calc, fc, "force_constants")
    post = _process(orm, orm.CalcFunctionNode, "PhonopyCalculation", caller=wf,
                    inputs=[("force_constants", g["force_constants"])])
    ph_bands = orm.BandsData()
    ph_bands.set_cell(cu.cell, pbc=cu.pbc)
    ph_bands.set_kpoints(k)                         # the fcc path above, primitive reciprocal cell
    ph_bands.set_bands(np.zeros((len(k), 3)), units="THz")
    ph_bands.labels = bands.labels
    g["phonon_bands"] = _create(post, ph_bands, "phonon_bands")
    return g
