"""A stand-in for mp-api's ``MPRester`` that answers with real pymatgen objects (Si), so the
tests check the conversions without the internet or an API key."""
import numpy as np
import pytest


def si():
    from pymatgen.core import Lattice, Structure

    a = 5.43
    return Structure(Lattice([[0, a / 2, a / 2], [a / 2, 0, a / 2], [a / 2, a / 2, 0]]), ["Si", "Si"],
                     [[0, 0, 0], [0.25, 0.25, 0.25]])


def band_structure():
    from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
    from pymatgen.electronic_structure.core import Spin

    s = si()
    G, X, U, K = [0, 0, 0], [0.5, 0, 0.5], [0.625, 0.25, 0.625], [0.375, 0.375, 0.75]
    # G-X | U-G (a break between X and U), 4 points per line
    line = lambda p, q: [list(np.add(p, np.multiply(t, np.subtract(q, p)))) for t in np.linspace(0, 1, 4)]
    kpts = line(G, X) + line(U, G)
    nk = len(kpts)
    bands = np.array([np.linspace(-6, -1, nk), np.linspace(-2, 0, nk), np.linspace(1, 3, nk)])  # (nb, nk)
    labels = {"\\Gamma": G, "X": X, "U": U}
    return BandStructureSymmLine(kpts, {Spin.up: bands}, s.lattice.reciprocal_lattice, 0.0, labels, structure=s)


def complete_dos():
    from pymatgen.electronic_structure.core import Orbital, Spin
    from pymatgen.electronic_structure.dos import CompleteDos, Dos

    s = si()
    e = np.linspace(-10, 5, 31)
    total = Dos(0.5, e, {Spin.up: np.exp(-(e + 3) ** 2), Spin.down: np.exp(-(e + 2) ** 2)})
    pdos = {site: {Orbital.s: {Spin.up: 0.1 * np.ones_like(e), Spin.down: 0.2 * np.ones_like(e)},
                   Orbital.px: {Spin.up: 0.3 * np.ones_like(e), Spin.down: 0.4 * np.ones_like(e)}} for site in s}
    return CompleteDos(s, total, pdos)


def chgcar():
    from pymatgen.io.vasp import Chgcar, Poscar

    s = si()
    x = np.arange(4 * 5 * 6, dtype=float).reshape(4, 5, 6)
    return Chgcar(Poscar(s), {"total": x, "diff": 0.5 * x})


TRAJ = {"elements": [14, 14], "num_ionic_steps": 3,
        "cart_coords": [[[0, 0, 0], [1.40, 1.36, 1.36]], [[0, 0, 0], [1.37, 1.36, 1.36]], [[0, 0, 0], [1.3575] * 3]],
        "lattice": [si().lattice.matrix.tolist()] * 3,
        "energy": [-10.70, -10.83, -10.85],
        "forces": [[[0.1, 0, 0], [-0.1, 0, 0]], [[0.02, 0, 0], [-0.02, 0, 0]], [[0, 0, 0], [0, 0, 0]]]}


class _Summary:
    def __init__(self, log):
        self.log = log

    def search(self, **kw):
        self.log.append(("summary", kw))
        docs = [{"material_id": "mp-149", "formula_pretty": "Si", "nsites": 2, "energy_above_hull": 0.0,
                 "band_gap": 0.85, "symmetry": {"symbol": "Fd-3m"}, "theoretical": False},
                {"material_id": "mp-1056579", "formula_pretty": "Si", "nsites": 4, "energy_above_hull": 0.12,
                 "band_gap": None, "symmetry": {"symbol": "P6_3/mmc"}, "theoretical": True}]
        return [d for d in docs if not kw.get("is_stable") or d["energy_above_hull"] == 0]


class _Tasks:
    def __init__(self, log):
        self.log = log

    def get_trajectory(self, task_id, run_type=None):
        self.log.append(("trajectory", task_id))
        return dict(TRAJ)


class _Materials:
    def __init__(self, log):
        self.log = log
        self.summary, self.tasks = _Summary(log), _Tasks(log)

    def search(self, material_ids=None, fields=None, **kw):
        self.log.append(("materials", material_ids, fields))
        return [{"calc_types": {"mp-1000": "GGA Structure Optimization", "mp-2000": "r2SCAN Structure Optimization",
                                "mp-1500": "GGA+U Structure Optimization", "mp-3000": "GGA Static"}}]


class FakeMPRester:
    def __init__(self, log, key):
        self.log, self.key = log, key
        self.materials = _Materials(log)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_structure_by_material_id(self, mid, final=True, conventional_unit_cell=False):
        self.log.append(("structure", mid, final, conventional_unit_cell))
        if mid == "mp-0":
            raise RuntimeError("MPRestError: no document mp-0")
        return si() if final else [si(), si()]

    def get_bandstructure_by_material_id(self, mid):
        return band_structure()

    def get_dos_by_material_id(self, mid):
        return complete_dos()

    def get_charge_density_from_material_id(self, mid):
        return chgcar()


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("EWALD_CONFIG_DIR", str(tmp_path / "ewald-config"))
    return tmp_path / "ewald-config"


@pytest.fixture
def mp(monkeypatch):
    """``ewald_mp.client.rester`` answers with :class:`FakeMPRester`; ``mp.log`` records the calls."""
    pytest.importorskip("pymatgen")
    from ewald_mp import client

    log = []
    monkeypatch.setattr(client, "rester", lambda: FakeMPRester(log, client.api_key()))
    monkeypatch.setattr(client, "api_key", lambda: "test-key")
    return type("MP", (), {"log": log})
