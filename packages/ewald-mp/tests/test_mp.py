import json

import numpy as np
import pytest

from ewald import load
from ewald_mp import criteria, parse, search


# ------------------------------------------------------------------ addresses and queries
def test_parse():
    assert parse("mp:mp-149") == ("mp-149", "structure")
    assert parse("mp:MP-149/Bands") == ("mp-149", "bands")
    assert parse("mp:149/dos") == ("mp-149", "dos")
    assert parse("mp:mp-149/relax/") == ("mp-149", "relax")
    with pytest.raises(ValueError, match="unknown view"):
        parse("mp:mp-149/phonons")
    with pytest.raises(ValueError):
        parse("mp:")


@pytest.mark.parametrize("text, crit", [
    ("LiFePO4", {"formula": "LiFePO4"}),
    ("ABO3", {"formula": "ABO3"}),
    ("Li-P-S", {"chemsys": "Li-P-S"}),
    ("Li P S", {"elements": ["Li", "P", "S"]}),
    ("Li,S", {"elements": ["Li", "S"]}),
    ("mp-149", {"material_ids": ["mp-149"]}),
    ("mp-149, MP-13", {"material_ids": ["mp-149", "mp-13"]}),
])
def test_criteria(text, crit):
    assert criteria(text) == crit


# ------------------------------------------------------------------ the key
def test_key_lives_in_the_keychain(config):
    from ewald import plugins
    from ewald_mp import client

    page = plugins.settings_pages()["mp"]
    page.save({"api_key": "abc123", "page_size": 10})
    assert client.api_key() == "abc123"
    stored = (config / "plugin-settings" / "mp.json").read_text(encoding="utf-8")
    assert "abc123" not in stored and json.loads(stored)["page_size"] == 10
    assert client.page_size() == 10


def test_missing_key_says_where_to_set_it(monkeypatch):
    from ewald_mp import client

    class Refuses:
        def __init__(self, *a, **k):
            raise ValueError("Please obtain a valid API key from https://materialsproject.org/api")

    import sys
    import types

    monkeypatch.setattr(client, "trust_system_store", lambda: False)
    fake = types.ModuleType("mp_api.client")
    fake.MPRester = Refuses
    monkeypatch.setitem(sys.modules, "mp_api", types.ModuleType("mp_api"))
    monkeypatch.setitem(sys.modules, "mp_api.client", fake)
    with pytest.raises(client.MPKeyError, match="Preferences › Materials Project"):
        client.rester()


# ------------------------------------------------------------------ against the stand-in
def test_structure(mp):
    data = load("mp:mp-149").compute(0)
    assert list(data.types) == ["Si", "Si"] and data.cell.pbc.all()
    assert np.allclose(data.positions[1], [1.3575] * 3)
    assert data.attributes["Materials Project"] == {"material_id": "mp-149", "view": "structure",
                                                   "uri": "mp:mp-149"}
    load("mp:mp-149", conventional=True).compute(0)
    assert ("structure", "mp-149", True, True) in mp.log


def test_initial_structures(mp):
    assert load("mp:mp-149/initial").num_frames == 2


def test_bands(mp):
    data = load("mp:mp-149/bands").compute(0)
    es = data.attributes["Electronic Structure"]
    assert es.eigenvalues.shape == (1, 8, 3)
    assert es.breaks == [4]                                  # X | U is not one line
    labels = [lab for _, lab in es.ticks]
    assert labels == ["Γ", "X|U", "Γ"]
    assert "Bands" in data.tables and data.attributes["Band Gap"] == pytest.approx(1.0)


def test_dos(mp):
    data = load("mp:mp-149/dos").compute(0)
    es = data.attributes["Electronic Structure"]
    assert es.dos.shape == (2, 31) and es.efermi == 0.5
    assert es.pdos.shape == (2, 2, 2, 31) and es.orbitals == ["s", "px"]
    table = data.tables["DOS"]
    assert {"Total (up)", "Total (down)", "Si (up)", "Si s (up)", "Si p (down)"} <= set(table)
    assert np.allclose(table["Si p (down)"], -0.8)           # two atoms, px 0.4 each, negated


def test_electronic_has_both(mp):
    es = load("mp:mp-149/electronic").compute(0).attributes["Electronic Structure"]
    assert es.has_bands and es.has_dos and es.efermi == 0.0   # the band structure's Fermi level
    assert es.dos.shape == (1, 31) and es.pdos.shape[1] == 1     # spin DOS summed to the bands' one channel


def test_charge_density_matches_the_chgcar_reader(mp, tmp_path):
    from conftest import chgcar

    data = load("mp:mp-149/chgcar").compute(0)
    grid = data.grids["charge-density"]
    chgcar().write_file(str(tmp_path / "CHGCAR"))
    ref = load(str(tmp_path / "CHGCAR")).compute(0).grids["charge-density"]
    assert grid.shape == ref.shape == (4, 5, 6)
    assert np.allclose(grid["Charge Density"], ref["Charge Density"], rtol=1e-4)
    assert np.allclose(grid["Magnetization"], ref["Magnetization"], rtol=1e-4)


def test_relaxation(mp):
    pipe = load("mp:mp-149/relax")
    assert pipe.num_frames == 3
    last = pipe.compute(2)
    assert last.attributes["Energy"] == -10.85 and last.attributes["Timestep"] == 3
    assert last.attributes["Materials Project"]["task_id"] == "mp-2000"      # r2SCAN first
    assert np.allclose(pipe.compute(0).particles["Force"][0], [0.1, 0, 0])
    load("mp:mp-149/relax", run_type="GGA").compute(0)
    assert ("trajectory", "mp-1000") in mp.log
    load("mp:mp-149/relax", task="mp-7").compute(0)
    assert ("trajectory", "mp-7") in mp.log


def test_errors_are_readable(mp):
    with pytest.raises(Exception, match="no document mp-0"):
        load("mp:mp-0").compute(0)


def test_search(mp):
    res = search("Si")
    assert [h.uri for h in res] == ["mp:mp-149", "mp:mp-1056579"]
    assert res[0].spacegroup == "Fd-3m" and res[1].band_gap is None
    kw = mp.log[-1][1]
    assert kw["formula"] == "Si" and "material_id" in kw["fields"]
    assert [h.material_id for h in search("Si", is_stable=True)] == ["mp-149"]
    assert "2 materials" in repr(res)


def test_ai_tool(mp):
    from ewald.llm.tools import Toolset

    res = Toolset().call("mp_search", {"query": "Si", "energy_above_hull": [0, 0.05], "is_stable": True})
    assert not res.is_error, res.content
    got = json.loads(res.content) if isinstance(res.content, str) else res.content
    assert got["hits"][0]["uri"] == "mp:mp-149"
    assert mp.log[-1][1]["energy_above_hull"] == (0.0, 0.05)
    assert "test-key" not in json.dumps(got)


def test_cli(mp, capsys):
    from ewald_mp.__main__ import main

    assert main(["search", "Si", "--stable", "--json"]) == 0
    assert [h["material_id"] for h in json.loads(capsys.readouterr().out)] == ["mp-149"]


def test_plugin_is_registered():
    from ewald import plugins

    p = plugins.installed()["mp"]
    assert p.loaded and not p.errors
    assert set(p.contributions) >= {"readers", "tools", "panels", "settings_pages"}
    assert plugins.scheme_reader("mp:mp-149").name == "mp"
    assert plugins.scheme_reader("C:\\data\\POSCAR") is None          # a Windows drive is no scheme


# ------------------------------------------------------------------ side bar
class _Context:
    def __init__(self):
        self.opened, self.cells, self.prefs = [], [], []

    def open(self, path):
        self.opened.append(path)

    def insert_cell(self, code):
        self.cells.append(code)

    def open_preferences(self, page=None):
        self.prefs.append(page)

    def on(self, event, fn):
        pass


def test_side_bar(mp, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets

    from ewald_mp.panel import materials_project

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctx = _Context()
    panel = materials_project(ctx)
    assert panel.who.text() == "API key set"
    panel.search.setText("Si")
    panel.run_search()
    panel.wait()
    app.processEvents()
    assert panel.tree.topLevelItemCount() == 2
    assert panel.tree.topLevelItem(0).text(3) == "0.000"
    panel.tree.topLevelItem(0).setSelected(True)
    panel.view.setCurrentIndex(panel.view.findData("/bands"))
    panel.open()
    panel.insert_cell()
    assert ctx.opened == ["mp:mp-149/bands"]
    assert ctx.cells == ['pipe = load("mp:mp-149/bands")  # Si']
    panel.tree.selectAll()
    panel.insert_cell()
    assert ctx.cells[-1].splitlines()[-1] == "pipe = mp_149"
    panel.key_button.click()
    assert ctx.prefs == ["Materials Project"]
    panel.search.setText("")
    panel.run_search()
    panel.wait()
    app.processEvents()
    assert "type a formula" in panel.note.text()


# ------------------------------------------------------------------ certificates behind a proxy
def _fake_mp_api(monkeypatch, order, error=None):
    import sys
    import types

    class Rester:
        def __init__(self, *a, **k):
            order.append("MPRester")
            if error:
                raise error

    fake = types.ModuleType("mp_api.client")
    fake.MPRester = Rester
    monkeypatch.setitem(sys.modules, "mp_api", types.ModuleType("mp_api"))
    monkeypatch.setitem(sys.modules, "mp_api.client", fake)


def test_system_store_is_used_before_mp_api(monkeypatch):
    truststore = pytest.importorskip("truststore")
    from ewald_mp import client

    order = []
    monkeypatch.setattr(client, "_trust_injected", False)
    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: order.append("inject"))
    _fake_mp_api(monkeypatch, order)
    client.rester()
    client.rester()
    assert order == ["inject", "MPRester", "MPRester"]          # once, and before mp-api connects


def test_system_store_can_be_turned_off(monkeypatch):
    truststore = pytest.importorskip("truststore")
    from ewald import plugins
    from ewald_mp import client

    plugins.settings_pages()["mp"].save({"system_certificates": False})
    monkeypatch.setattr(client, "_trust_injected", False)
    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: pytest.fail("injected although turned off"))
    assert client.trust_system_store() is False


def test_certificate_error_says_what_to_do(monkeypatch):
    pytest.importorskip("truststore")
    from ewald_mp import client

    monkeypatch.setattr(client, "trust_system_store", lambda: False)
    err = OSError("HTTPSConnectionPool(host='api.materialsproject.org', port=443): Max retries exceeded with url: "
                  "/heartbeat (Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] "
                  "certificate verify failed: unable to get local issuer certificate')))")
    _fake_mp_api(monkeypatch, [], err)
    with pytest.raises(ConnectionError, match="system certificate store"):
        client.rester()
