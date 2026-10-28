"""The Materials Project without mp-api: its REST API and its open data on S3, through urllib.

``Rester`` answers the handful of ``MPRester`` calls the plugin makes (``materials.summary.search``,
``materials.search``, ``get_structure_by_material_id``, ``get_bandstructure_by_material_id``,
``get_dos_by_material_id``, ``get_charge_density_from_material_id``) with plain JSON dicts in
pymatgen's ``as_dict()`` layout, which :mod:`ewald_mp.convert` reads without pymatgen. So the
plugin needs nothing beyond EWALD and ``truststore``.

- Searches and structures: ``https://api.materialsproject.org/materials/...`` with the key in
  the ``X-API-Key`` header (``_fields``, ``_limit``, ``_skip`` as mp-api sends them).
- Band structures, DOS and charge densities: the task ids come from the REST API, the data from
  MP's public bucket ``materialsproject-parsed`` (``bandstructures/``, ``dos/``, ``chgcars/``
  ``<task>.json.gz``, the files mp-api read before version 0.42; no key needed). Calculations
  newer than those files are only in MP's Delta tables, which need mp-api (``ewald-mp[full]``).
- Relaxation trajectories are only in those tables: :meth:`Tasks.get_trajectory` says to
  install ``ewald-mp[full]``.

HTTPS uses the operating system's certificate store (``truststore``) unless "Use the system
certificate store" is turned off; ``HTTPS_PROXY`` is honoured by urllib.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("MP_API_ENDPOINT") or "https://api.materialsproject.org/"
OPEN_DATA = "https://materialsproject-parsed.s3.amazonaws.com/"
TIMEOUT = 120
FULL_HINT = 'install mp-api for it (pip install mp-api, or pip install "ewald-mp[full]")'
_TASK = re.compile(r"^(mp|mvc)-\d+$", re.I)


class NeedsMPApi(RuntimeError):
    """What was asked for is only in MP's Delta tables, which mp-api reads."""


def _ssl_context():
    import ssl

    from .client import settings

    if settings().get("system_certificates", True) is not False:
        try:
            import truststore
        except ImportError:
            pass
        else:
            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()


def _user_agent() -> str:
    from . import __version__

    try:
        from importlib.metadata import version

        core = version("ewald")
    except Exception:  # noqa: BLE001 (a frozen app without metadata)
        core = "?"
    return f"ewald/{core} ewald-mp/{__version__}"


def fetch(url: str, headers: dict | None = None) -> bytes:
    """The body of ``url`` (gunzipped when it is gzip). HTTP errors keep their code in
    :class:`HTTPError`; a refused certificate says what to do."""
    from .client import CERT_HINT, _cert_error

    if not url.lower().startswith(("https://", "http://127.0.0.1:")):      # a local server only in tests
        raise ValueError(f"not an https address: {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": _user_agent(), "Accept": "application/json",
                                                   **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT,
                                    context=_ssl_context() if url.lower().startswith("https:") else None) as r:
            body = r.read()
    except urllib.error.HTTPError as exc:
        raise HTTPError(exc.code, url, _detail(exc.read()) or str(exc.reason)) from None
    except (urllib.error.URLError, OSError) as exc:
        reason = str(getattr(exc, "reason", exc))
        if _cert_error(reason) or _cert_error(repr(exc)):
            raise ConnectionError(f"Materials Project: {CERT_HINT}") from None
        raise ConnectionError(f"Materials Project: {url.split('?')[0]} could not be reached ({reason})") from None
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


class HTTPError(RuntimeError):
    def __init__(self, code: int, url: str, detail: str):
        super().__init__(f"{code} {detail} ({url.split('?')[0]})")
        self.code = code


def _detail(body: bytes) -> str:
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ""
    if isinstance(doc, dict):
        d = doc.get("detail") or doc.get("message") or doc.get("error")
        return d if isinstance(d, str) else json.dumps(d)[:300] if d else ""
    return ""


def env_key() -> str | None:
    """The key mp-api would find without EWALD: ``MP_API_KEY``, then ``PMG_MAPI_KEY`` in
    ``~/.pmgrc.yaml``."""
    if key := os.environ.get("MP_API_KEY", "").strip():
        return key
    rc = Path.home() / ".pmgrc.yaml"
    try:
        text = rc.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^\s*PMG_MAPI_KEY\s*:\s*['\"]?([^'\"\s#]+)", text, re.M)
    return m.group(1) if m else None


def _param(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    return str(value)


class Rester:
    """The REST API with ``api_key``; ``endpoint`` and ``open_data`` are for tests."""

    def __init__(self, api_key: str | None, endpoint: str | None = None, open_data: str | None = None):
        self.api_key = api_key
        self.endpoint = (endpoint or API).rstrip("/") + "/"
        self.open_data = (open_data or OPEN_DATA).rstrip("/") + "/"
        self.materials = Materials(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    # ------------------------------------------------------------------ transport
    def get(self, route: str, **params) -> list[dict]:
        """``data`` of ``GET <endpoint><route>/?params``."""
        from .client import MPKeyError, KEY_URL

        if not self.api_key:
            raise MPKeyError(f"no Materials Project API key: set it under Preferences › Materials Project "
                             f"(get one at {KEY_URL})")
        query = urllib.parse.urlencode({k: _param(v) for k, v in params.items() if v is not None})
        url = f"{self.endpoint}{route.strip('/')}/" + (f"?{query}" if query else "")
        try:
            body = fetch(url, {"X-API-Key": self.api_key})
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise MPKeyError(f"the Materials Project refused the API key ({exc}); check it under "
                                 "Preferences › Materials Project") from None
            raise RuntimeError(f"Materials Project: {exc}") from None
        doc = json.loads(body.decode("utf-8"))
        data = doc.get("data") if isinstance(doc, dict) else doc
        return list(data or [])

    def open_object(self, key: str) -> dict:
        """A ``.json.gz`` of MP's open data bucket (no key), ``None`` when it is not there."""
        try:
            return json.loads(fetch(self.open_data + key).decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (403, 404):      # S3 answers 403 for a missing key in a public bucket
                return None
            raise RuntimeError(f"Materials Project open data: {exc}") from None

    def _object(self, folder: str, task_id: str, what: str, material_id: str) -> dict:
        doc = self.open_object(f"{folder}/{task_id}.json.gz")
        if doc is None:
            raise NeedsMPApi(f"the {what} of {material_id} (task {task_id}) is not in MP's per-task open data "
                             f"files, only in its newer tables; {FULL_HINT}")
        return doc.get("data", doc)

    # ------------------------------------------------------------------ what the plugin calls
    def get_structure_by_material_id(self, material_id: str, final: bool = True,
                                     conventional_unit_cell: bool = False):
        field = "structure" if final else "initial_structures"
        docs = self.materials.search(material_ids=[material_id], fields=[field])
        got = docs[0].get(field) if docs else None
        if not got:
            raise ValueError(f"the Materials Project has no material {material_id}")
        if conventional_unit_cell:
            from .convert import conventional

            got = [conventional(s) for s in got] if isinstance(got, list) else conventional(got)
        return got

    def _es(self, material_id: str, field: str):
        docs = self.get("materials/electronic_structure", material_ids=material_id, _fields=field, _limit=1)
        return docs[0].get(field) if docs else None

    def get_bandstructure_by_material_id(self, material_id: str, path_type: str = "setyawan_curtarolo"):
        bs = self._es(material_id, "bandstructure") or {}
        entry = bs.get(path_type) or next((v for v in bs.values() if isinstance(v, dict) and v.get("task_id")), None)
        if not entry or not entry.get("task_id"):
            return None
        return self._object("bandstructures", str(entry["task_id"]), "band structure", material_id)

    def get_dos_by_material_id(self, material_id: str):
        dos = self._es(material_id, "dos") or {}
        task = dos.get("task_id")
        if not task:      # older documents keep it per spin: dos.total["1"].task_id
            total = dos.get("total") or {}
            task = next((v.get("task_id") for v in total.values() if isinstance(v, dict) and v.get("task_id")), None)
        if not task:
            return None
        return self._object("dos", str(task), "density of states", material_id)

    def get_charge_density_from_material_id(self, material_id: str):
        """The newest GGA or GGA+U static calculation's charge density, as mp-api picks it."""
        docs = self.materials.search(material_ids=[material_id], fields=["calc_types"])
        calc = (docs[0].get("calc_types") if docs else None) or {}
        tasks = [t for t, c in calc.items() if str(c) in ("GGA Static", "GGA+U Static")]
        if not tasks:
            return None
        try:
            dated = self.get("materials/tasks", task_ids=tasks, _fields="task_id,last_updated", _limit=len(tasks))
            order = [d["task_id"] for d in sorted(dated, key=lambda d: str(d.get("last_updated")), reverse=True)]
        except Exception:  # noqa: BLE001 (fall back to the highest task number)
            order = []
        order += sorted((t for t in tasks if t not in order), key=_task_number, reverse=True)
        for task in order:
            doc = self.open_object(f"chgcars/{task}.json.gz")
            if doc is not None:
                return doc.get("data", doc)
        raise NeedsMPApi(f"no charge density of {material_id} in MP's open data files (tasks {', '.join(order)})")


def _task_number(task: str) -> int:
    digits = re.sub(r"\D", "", task)
    return int(digits) if digits else -1


class Materials:
    def __init__(self, rester: Rester):
        self.rester = rester
        self.summary = Summary(rester)
        self.tasks = Tasks(rester)

    def search(self, material_ids=None, fields=None, **criteria):
        """``materials/core`` documents (mp-api's ``materials.search``)."""
        return self.rester.get("materials/core", material_ids=material_ids, _fields=fields,
                               _limit=len(material_ids) if material_ids else None, **criteria)


#: summary.search arguments given as (min, max) that the REST API takes as ``<name>_min``/``_max``
RANGES = {"energy_above_hull", "band_gap", "formation_energy", "formation_energy_per_atom", "density",
          "volume", "nsites", "num_sites", "nelements", "num_elements", "total_magnetization", "efermi",
          "energy_per_atom", "uncorrected_energy_per_atom", "equilibrium_reaction_energy_per_atom",
          "k_vrh", "g_vrh", "e_total", "n", "weighted_surface_energy", "weighted_work_function"}
_ALIASES = {"num_sites": "nsites", "num_elements": "nelements", "formation_energy": "formation_energy_per_atom",
            "total_energy": "energy_per_atom"}


class Summary:
    def __init__(self, rester: Rester):
        self.rester = rester

    def search(self, fields=None, num_chunks=None, chunk_size: int = 1000, **criteria):
        """``materials/summary`` documents (mp-api's ``materials.summary.search``): ranges as
        ``(min, max)``, lists comma separated, the first ``chunk_size`` hits."""
        params = {}
        for name, value in criteria.items():
            if value is None:
                continue
            key = _ALIASES.get(name, name)
            if name in RANGES and isinstance(value, (tuple, list)):
                params[f"{key}_min"], params[f"{key}_max"] = value[0], value[1]
            elif name == "material_ids":
                params[key] = [value] if isinstance(value, str) else list(value)
            else:
                params[key] = value
        return self.rester.get("materials/summary", _fields=fields, _limit=max(1, min(int(chunk_size), 1000)),
                               **params)


class Tasks:
    def __init__(self, rester: Rester):
        self.rester = rester

    def get_trajectory(self, task_id, run_type=None):
        raise NeedsMPApi(f"relaxation trajectories are only in MP's Delta tables, which need mp-api: {FULL_HINT}")
