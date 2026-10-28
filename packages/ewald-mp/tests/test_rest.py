"""Without mp-api: the REST API and MP's open data through urllib (a local server stands in)."""
import json

import numpy as np
import pytest

from ewald import load
from ewald_mp import search


def test_no_mp_api_means_rest(monkeypatch):
    from ewald_mp import client, rest

    monkeypatch.setattr(client, "has_mp_api", lambda: False)
    assert client.backend() == "rest" and isinstance(client.rester(), rest.Rester)


def test_mp_api_can_be_turned_off(monkeypatch):
    from ewald import plugins
    from ewald_mp import client

    monkeypatch.setattr(client, "has_mp_api", lambda: True)
    assert client.backend() == "mp-api"
    plugins.settings_pages()["mp"].save({"use_mp_api": False})
    assert client.backend() == "rest"


def test_structure(rest):
    data = load("mp:mp-149").compute(0)
    assert list(data.types) == ["Si", "Si"] and data.cell.pbc.all()
    assert np.allclose(data.positions[1], [1.3575] * 3)
    assert data.attributes["Materials Project"]["view"] == "structure"
    path, q, key = rest.requests[-1]
    assert path == "/materials/core/" and q["material_ids"] == "mp-149" and q["_fields"] == "structure"
    assert key == "test-key"


def test_conventional_cell(rest):
    data = load("mp:mp-149", conventional=True).compute(0)
    assert data.count == 8 and np.allclose(np.abs(np.linalg.det(data.cell.matrix)), 5.43 ** 3)


def test_initial_structures(rest):
    assert load("mp:mp-149/initial").num_frames == 2


def test_bands(rest):
    data = load("mp:mp-149/bands").compute(0)
    es = data.attributes["Electronic Structure"]
    assert es.eigenvalues.shape == (1, 8, 3)
    assert es.breaks == [4]                                  # X | U is not one line
    assert [lab for _, lab in es.ticks] == ["Γ", "X|U", "Γ"]
    assert data.attributes["Band Gap"] == pytest.approx(1.0)
    assert ("/open/bandstructures/mp-1001.json.gz", {}, None) in rest.requests   # open data: no key sent


def test_dos(rest):
    data = load("mp:mp-149/dos").compute(0)
    es = data.attributes["Electronic Structure"]
    assert es.dos.shape == (2, 31) and es.efermi == 0.5
    assert es.pdos.shape == (2, 2, 2, 31) and es.orbitals == ["s", "px"]
    assert np.allclose(data.tables["DOS"]["Si p (down)"], -0.8)


def test_electronic_has_both(rest):
    es = load("mp:mp-149/electronic").compute(0).attributes["Electronic Structure"]
    assert es.has_bands and es.has_dos and es.efermi == 0.0
    assert es.dos.shape == (1, 31)


def test_charge_density(rest):
    data = load("mp:mp-149/chgcar").compute(0)
    grid = data.grids["charge-density"]
    volume = abs(np.linalg.det(data.cell.matrix))
    x = np.arange(120.0).reshape(4, 5, 6)
    assert grid.shape == (4, 5, 6)
    assert np.allclose(grid["Charge Density"], x / volume) and np.allclose(grid["Magnetization"], 0.5 * x / volume)
    # the newest GGA static (by last_updated), not r2SCAN
    assert any(p == "/open/chgcars/mp-3000.json.gz" for p, _, _ in rest.requests)


def test_missing_open_data_says_install_mp_api(rest):
    from ewald_mp.rest import NeedsMPApi

    rest.objects.pop("bandstructures/mp-1001.json.gz")
    with pytest.raises(NeedsMPApi, match="mp-api"):
        load("mp:mp-149/bands").compute(0)


def test_relax_needs_mp_api(rest):
    from ewald_mp.rest import NeedsMPApi

    with pytest.raises(NeedsMPApi, match="pip install mp-api"):
        load("mp:mp-149/relax")
    assert rest.requests == []                               # said before asking the server


def test_unknown_material(rest):
    with pytest.raises(ValueError, match="no material mp-0"):
        load("mp:mp-0")


def test_search(rest):
    res = search("Si", energy_above_hull=(0, 0.05), is_stable=True)
    assert [h.uri for h in res] == ["mp:mp-149"] and res[0].spacegroup == "Fd-3m"
    path, q, _ = rest.requests[-1]
    assert path == "/materials/summary/"
    assert q["formula"] == "Si" and q["is_stable"] == "true"
    assert q["energy_above_hull_min"] == "0" and q["energy_above_hull_max"] == "0.05"
    assert "material_id" in q["_fields"].split(",") and q["_limit"] == "25"
    search("Li P S")
    assert rest.requests[-1][1]["elements"] == "Li,P,S"
    search("mp-149, mp-13")
    assert rest.requests[-1][1]["material_ids"] == "mp-149,mp-13"


def test_ai_tool(rest):
    from ewald.llm.tools import Toolset

    res = Toolset().call("mp_search", {"query": "Si"})
    assert not res.is_error, res.content
    got = json.loads(res.content) if isinstance(res.content, str) else res.content
    assert got["hits"][0]["uri"] == "mp:mp-149" and "test-key" not in json.dumps(got)


def test_refused_key(rest, monkeypatch):
    from ewald_mp import client

    monkeypatch.setattr(client, "api_key", lambda: "wrong")
    with pytest.raises(client.MPKeyError, match="refused the API key"):
        search("Si")


def test_no_key(rest, monkeypatch):
    from ewald_mp import client, rest as rest_mod

    monkeypatch.setattr(client, "api_key", lambda: None)
    monkeypatch.setattr(rest_mod, "env_key", lambda: None)
    with pytest.raises(client.MPKeyError, match="Preferences › Materials Project"):
        search("Si")


def test_key_from_mp_api_places(monkeypatch, tmp_path):
    from ewald_mp import rest

    monkeypatch.delenv("MP_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))          # Path.home() on Windows
    assert rest.env_key() is None
    (tmp_path / ".pmgrc.yaml").write_bytes(b"PMG_VASP_PSP_DIR: /x\r\nPMG_MAPI_KEY: 'abc123'\r\n")   # CRLF too
    assert rest.env_key() == "abc123"
    monkeypatch.setenv("MP_API_KEY", "env456")
    assert rest.env_key() == "env456"


def test_certificate_error_says_what_to_do(monkeypatch):
    import ssl
    import urllib.error
    import urllib.request

    from ewald_mp import rest

    def refuse(*a, **k):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate "
                                                                    "verify failed: unable to get local issuer"))

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(ConnectionError, match="system certificate store"):
        rest.fetch("https://api.materialsproject.org/materials/summary/")


def test_only_https(monkeypatch):
    from ewald_mp import rest

    for url in ("file:///etc/passwd", "http://example.org/x"):
        with pytest.raises(ValueError, match="https"):
            rest.fetch(url)


def test_system_store_is_used(monkeypatch):
    truststore = pytest.importorskip("truststore")
    from ewald import plugins
    from ewald_mp import rest

    assert isinstance(rest._ssl_context(), truststore.SSLContext)
    plugins.settings_pages()["mp"].save({"system_certificates": False})
    assert not isinstance(rest._ssl_context(), truststore.SSLContext)


def test_installs_nothing_heavy():
    """The point of 0.2: installing the plugin pulls in neither mp-api nor pymatgen."""
    from pathlib import Path

    try:
        import tomllib
    except ImportError:       # Python 3.10
        import tomli as tomllib

    deps = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    names = [d.split(">")[0].split("=")[0].split(";")[0].strip().lower() for d in deps["project"]["dependencies"]]
    assert not {"mp-api", "pymatgen", "emmet-core", "boto3", "requests"} & set(names)


@pytest.mark.parametrize("make", ["band_structure", "complete_dos", "chgcar"])
def test_dicts_read_like_the_objects(make):
    """pymatgen's ``as_dict()`` of the mp-api objects gives the same frames as the objects."""
    pytest.importorskip("pymatgen")
    import conftest
    from ewald.electronic import ElectronicStructure
    from ewald_mp import convert as C

    from monty.json import MontyEncoder

    obj = getattr(conftest, make)()
    as_json = json.loads(json.dumps(obj.as_dict(), cls=MontyEncoder))      # as the open data files hold it
    if make == "chgcar":
        a, b = C.charge_density(obj), C.charge_density(as_json)
        assert np.allclose(a.grids["charge-density"]["Charge Density"], b.grids["charge-density"]["Charge Density"])
        return
    fill = C.bands if make == "band_structure" else (lambda o, es: C.dos(o, es, 2))
    a, b = fill(obj, ElectronicStructure(types=["Si", "Si"])), fill(as_json, ElectronicStructure(types=["Si", "Si"]))
    for name in ("eigenvalues", "distances", "dos", "pdos"):
        x, y = getattr(a, name, None), getattr(b, name, None)
        assert (x is None) == (y is None) and (x is None or np.allclose(x, y)), name
    assert a.ticks == b.ticks and a.breaks == b.breaks and a.efermi == b.efermi
