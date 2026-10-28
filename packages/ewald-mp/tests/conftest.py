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
        "lattice": [[[0, 2.715, 2.715], [2.715, 0, 2.715], [2.715, 2.715, 0]]] * 3,
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


# ------------------------------------------------------------------ without mp-api: REST + open data
# The same Si data as above in pymatgen's as_dict() layout, as the REST API and MP's open data
# bucket send it (no pymatgen needed), served by a local HTTP server.
A = 5.43
LATTICE = [[0, A / 2, A / 2], [A / 2, 0, A / 2], [A / 2, A / 2, 0]]


def si_dict():
    m = np.array(LATTICE)
    sites = []
    for abc in ([0, 0, 0], [0.25, 0.25, 0.25]):
        sites.append({"species": [{"element": "Si", "occu": 1}], "abc": abc, "xyz": list(np.array(abc) @ m),
                      "label": "Si", "properties": {}})
    return {"@module": "pymatgen.core.structure", "@class": "Structure", "charge": 0,
            "lattice": {"matrix": LATTICE}, "sites": sites}


def bands_dict():
    """As the open data's bandstructures/<task>.json.gz: no structure, k-points without labels."""
    G, X, U = [0, 0, 0], [0.5, 0, 0.5], [0.625, 0.25, 0.625]
    line = lambda p, q: [list(np.add(p, np.multiply(t, np.subtract(q, p)))) for t in np.linspace(0, 1, 4)]
    kpts = line(G, X) + line(U, G)
    nk = len(kpts)
    bands = [list(np.linspace(-6, -1, nk)), list(np.linspace(-2, 0, nk)), list(np.linspace(1, 3, nk))]
    rec = (2 * np.pi * np.linalg.inv(np.array(LATTICE)).T).tolist()
    return {"@module": "pymatgen.electronic_structure.bandstructure", "@class": "BandStructureSymmLine",
            "lattice_rec": {"matrix": rec}, "efermi": 0.0, "kpoints": kpts,
            "branches": [{"start_index": 0, "end_index": nk - 1, "name": "\\Gamma-None"}],   # as broken as MP's
            "bands": {"1": bands}, "labels_dict": {"\\Gamma": G, "X": X, "U": U}, "is_spin_polarized": False}


def dos_dict():
    e = np.linspace(-10, 5, 31)
    ones = np.ones_like(e)
    pdos = [{"s": {"densities": {"1": list(0.1 * ones), "-1": list(0.2 * ones)}},
             "px": {"densities": {"1": list(0.3 * ones), "-1": list(0.4 * ones)}}} for _ in range(2)]
    return {"@module": "pymatgen.electronic_structure.dos", "@class": "CompleteDos", "efermi": 0.5,
            "structure": si_dict(), "energies": list(e),
            "densities": {"1": list(np.exp(-(e + 3) ** 2)), "-1": list(np.exp(-(e + 2) ** 2))}, "pdos": pdos}


def chgcar_dict():
    x = np.arange(4 * 5 * 6, dtype=float).reshape(4, 5, 6)
    arr = lambda a: {"@module": "numpy", "@class": "array", "dtype": "float64", "data": a.tolist()}
    return {"@module": "pymatgen.io.vasp.outputs", "@class": "Chgcar",
            "poscar": {"structure": si_dict()}, "data": {"total": arr(x), "diff": arr(0.5 * x)}}


SUMMARY = [{"material_id": "mp-149", "formula_pretty": "Si", "nsites": 2, "energy_above_hull": 0.0,
            "band_gap": 0.85, "symmetry": {"symbol": "Fd-3m"}, "theoretical": False},
           {"material_id": "mp-1056579", "formula_pretty": "Si", "nsites": 4, "energy_above_hull": 0.12,
            "band_gap": None, "symmetry": {"symbol": "P6_3/mmc"}, "theoretical": True}]


class MPServer:
    """``/materials/...`` as the REST API answers (key ``test-key``) and ``/open/...`` as the
    open data bucket; ``requests`` records (path, query, key header)."""

    def __init__(self):
        import gzip
        import json
        import threading
        import urllib.parse
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        server = self
        self.requests = []
        self.objects = {"bandstructures/mp-1001.json.gz": {"task_id": "mp-1001", "data": bands_dict()},
                        "dos/mp-1002.json.gz": {"task_id": "mp-1002", "data": dos_dict()},
                        "chgcars/mp-3000.json.gz": {"task_id": "mp-3000", "data": chgcar_dict()}}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, doc, gz=False):
                body = json.dumps(doc).encode()
                if gz:
                    body = gzip.compress(body)
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(url.query))
                key = self.headers.get("X-API-Key")
                server.requests.append((url.path, q, key))
                if url.path.startswith("/open/"):
                    obj = server.objects.get(url.path[len("/open/"):])
                    return self._send(200, obj, gz=True) if obj else self._send(403, {"error": "AccessDenied"})
                if key != "test-key":
                    return self._send(401, {"detail": "invalid API key"})
                return self._send(200, {"data": server.route(url.path, q), "meta": {}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    def route(self, path, q):
        ids = q.get("material_ids", "").split(",") if q.get("material_ids") else []
        if "mp-0" in ids:
            return []
        if path == "/materials/summary/":
            return [d for d in SUMMARY if q.get("is_stable") != "true" or d["energy_above_hull"] == 0]
        if path == "/materials/core/":
            field = q.get("_fields")
            if field == "structure":
                return [{"structure": si_dict()}]
            if field == "initial_structures":
                return [{"initial_structures": [si_dict(), si_dict()]}]
            if field == "calc_types":
                return [{"calc_types": {"mp-1000": "GGA Structure Optimization", "mp-2999": "GGA Static",
                                        "mp-3000": "GGA Static", "mp-4000": "r2SCAN Static"}}]
        if path == "/materials/electronic_structure/":
            if q.get("_fields") == "bandstructure":
                return [{"bandstructure": {"setyawan_curtarolo": {"task_id": "mp-1001"}, "hinuma": None}}]
            if q.get("_fields") == "dos":
                return [{"dos": {"total": {"1": {"task_id": "mp-1002"}}}}]
        if path == "/materials/tasks/":
            return [{"task_id": "mp-2999", "last_updated": "2020-01-01"}, {"task_id": "mp-3000", "last_updated": "2023-05-01"}]
        return []

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def rest(monkeypatch):
    """The plugin without mp-api, talking to :class:`MPServer` with the key ``test-key``."""
    from ewald_mp import client, rest as rest_mod

    srv = MPServer()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(client, "has_mp_api", lambda: False)
    monkeypatch.setattr(client, "api_key", lambda: "test-key")
    monkeypatch.setattr(rest_mod, "API", srv.url)
    monkeypatch.setattr(rest_mod, "OPEN_DATA", srv.url + "open/")
    yield srv
    srv.close()
