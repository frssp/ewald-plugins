"""Materials Project data as EWALD frames: pymatgen and emmet objects from mp-api, or the same
data as JSON dicts in pymatgen's ``as_dict()`` layout (:mod:`ewald_mp.rest`), read without pymatgen."""
from __future__ import annotations

import numpy as np

from ewald import Cell, DataCollection
from ewald.electronic import ElectronicStructure, merge_ticks, path_distances, pretty_label


def structure(s) -> DataCollection:
    """A pymatgen ``Structure`` or its dict (no ASE round trip, so site properties stay out of the way)."""
    if isinstance(s, dict):
        return _structure_dict(s)
    symbols = [site.specie.symbol if hasattr(site.specie, "symbol") else str(site.specie) for site in s]
    data = DataCollection(np.asarray(s.cart_coords, float).reshape(-1, 3), symbols,
                          Cell(np.asarray(s.lattice.matrix, float), pbc=True))
    magmom = s.site_properties.get("magmom") if hasattr(s, "site_properties") else None
    if magmom is not None and not any(m is None for m in magmom):
        data.particles["Magnetic Moment"] = np.asarray(magmom, float)
    return data


def _element(species: list) -> str:
    """The element of a site's ``species`` list (the most occupied one on a disordered site)."""
    best = max(species, key=lambda sp: float(sp.get("occu", 1.0)))
    return str(best.get("element") or best.get("label") or "X")


def _structure_dict(d: dict) -> DataCollection:
    matrix = np.asarray(d["lattice"]["matrix"], float)
    sites = d["sites"]
    symbols = [_element(site["species"]) for site in sites]
    if sites and all("xyz" in site for site in sites):
        pos = np.asarray([site["xyz"] for site in sites], float).reshape(-1, 3)
    else:
        pos = np.asarray([site["abc"] for site in sites], float).reshape(-1, 3) @ matrix
    data = DataCollection(pos, symbols, Cell(matrix, pbc=True))
    magmom = [(site.get("properties") or {}).get("magmom") for site in sites]
    if sites and not any(m is None for m in magmom):
        data.particles["Magnetic Moment"] = np.asarray(magmom, float)
    return data


def conventional(d: dict) -> dict:
    """A structure dict in its conventional standard cell (spglib, as pymatgen's
    ``get_conventional_standard_structure`` starts from)."""
    import spglib

    data = _structure_dict(d)
    from ase.data import atomic_numbers

    numbers = [atomic_numbers[t] for t in data.types]
    frac = data.positions @ np.linalg.inv(data.cell.matrix)
    got = spglib.standardize_cell((data.cell.matrix, frac, numbers), to_primitive=False, no_idealize=False,
                                  symprec=0.1)
    if got is None:
        return d
    lattice, frac, numbers = got
    from ase.data import chemical_symbols

    return {"lattice": {"matrix": np.asarray(lattice).tolist()},
            "sites": [{"species": [{"element": chemical_symbols[int(z)], "occu": 1}], "abc": list(map(float, f))}
                      for f, z in zip(frac, numbers)]}


def _array(x) -> np.ndarray:
    """A list, or monty's ``{"@module": "numpy", "@class": "array", "data": ...}``."""
    if isinstance(x, dict) and x.get("@class") == "array":
        return np.asarray(x["data"], dtype=x.get("dtype") or float)
    return np.asarray(x, float)


def _spin_keys(by_spin: dict) -> list[str]:
    """``"1"`` (up) then ``"-1"`` (down) of a JSON ``{spin: values}``."""
    return ["1"] + (["-1"] if "-1" in by_spin else [])


#: pymatgen orbital names that VASP (and so EWALD's orbital groups) spell differently
_ORBITAL = {"dx2_y2": "dx2", "f_3": "f-3", "f_2": "f-2", "f_1": "f-1"}


def orbital_name(orb) -> str:
    name = getattr(orb, "name", str(orb))
    return _ORBITAL.get(name, name)


def _spins(obj):
    from pymatgen.electronic_structure.core import Spin

    return [Spin.up] + ([Spin.down] if Spin.down in obj else [])


def bands(bs, es: ElectronicStructure) -> ElectronicStructure:
    """Fill ``es`` with a pymatgen ``BandStructure(SymmLine)`` or its dict: eigenvalues, the path, its labels."""
    if isinstance(bs, dict):
        return _bands_dict(bs, es)
    spins = _spins(bs.bands)
    es.eigenvalues = np.stack([np.asarray(bs.bands[s], float).T for s in spins])  # (nspin, nk, nb)
    es.kpoints = np.array([k.frac_coords for k in bs.kpoints], float)
    es.efermi = float(bs.efermi)
    branches = getattr(bs, "branches", None) or []
    starts = [int(b["start_index"]) for b in branches[1:]]
    lattice = bs.structure.lattice.matrix if getattr(bs, "structure", None) is not None \
        else np.linalg.inv(bs.lattice_rec.matrix / (2 * np.pi)).T
    es.distances, es.breaks = path_distances(es.kpoints, lattice, starts=starts or None)
    ticks = [(float(es.distances[i]), pretty_label(k.label)) for i, k in enumerate(bs.kpoints) if k.label]
    es.ticks = merge_ticks(ticks)
    return es


def kpoint_labels(kpoints, labels_dict: dict, tol: float = 1e-5) -> list:
    """The label of every k-point (``None`` off the high-symmetry points), as pymatgen gives them."""
    named = [(lab, np.asarray(k, float)) for lab, k in (labels_dict or {}).items()]
    out = []
    for k in np.asarray(kpoints, float):
        out.append(next((lab for lab, q in named if np.allclose(k, q, atol=tol)), None))
    return out


def line_starts(labels: list) -> list[int]:
    """Indices that start a new line: two labelled points in a row (pymatgen's branches); a
    repeated point (``X X``) gives no distance, a jump (``X|U``) a break."""
    return [i for i in range(1, len(labels)) if labels[i] is not None and labels[i - 1] is not None]


def _bands_dict(d: dict, es: ElectronicStructure) -> ElectronicStructure:
    spins = _spin_keys(d["bands"])
    es.eigenvalues = np.stack([_array(d["bands"][s]).T for s in spins])          # (nspin, nk, nb)
    es.kpoints = np.asarray(d["kpoints"], float)
    es.efermi = float(d["efermi"])
    if d.get("structure"):
        lattice = np.asarray(d["structure"]["lattice"]["matrix"], float)
    else:
        lattice = np.linalg.inv(np.asarray(d["lattice_rec"]["matrix"], float) / (2 * np.pi)).T
    labels = kpoint_labels(es.kpoints, d.get("labels_dict") or {})
    starts = line_starts(labels)
    es.distances, es.breaks = path_distances(es.kpoints, lattice, starts=starts or None)
    es.ticks = merge_ticks([(float(es.distances[i]), pretty_label(lab)) for i, lab in enumerate(labels) if lab])
    return es


def dos(d, es: ElectronicStructure, natoms: int) -> ElectronicStructure:
    """Fill ``es`` with a pymatgen ``Dos``/``CompleteDos``: the total DOS and, for a complete
    one, the projected DOS per site and orbital (VASP's lm names). Also their dicts."""
    if isinstance(d, dict):
        return _dos_dict(d, es, natoms)
    spins = _spins(d.densities)
    es.dos_energies = np.asarray(d.energies, float)
    es.dos = np.stack([np.asarray(d.densities[s], float) for s in spins])
    if es.eigenvalues is None:
        es.efermi = float(d.efermi)
    pdos = getattr(d, "pdos", None)
    if pdos and len(pdos) == natoms:
        sites = list(getattr(d, "structure", None) or pdos)
        orbitals = []
        for site in sites:
            for orb in pdos.get(site, {}):
                name = orbital_name(orb)
                if name not in orbitals:
                    orbitals.append(name)
        arr = np.zeros((natoms, len(spins), len(orbitals), len(es.dos_energies)))
        for i, site in enumerate(sites):
            for orb, by_spin in pdos.get(site, {}).items():
                j = orbitals.index(orbital_name(orb))
                for k, s in enumerate(spins):
                    if s in by_spin:
                        arr[i, k, j] = by_spin[s]
        es.pdos, es.orbitals = arr, orbitals
    return _match_spins(es)


def _dos_dict(d: dict, es: ElectronicStructure, natoms: int) -> ElectronicStructure:
    spins = _spin_keys(d["densities"])
    es.dos_energies = _array(d["energies"])
    es.dos = np.stack([_array(d["densities"][s]) for s in spins])
    if es.eigenvalues is None:
        es.efermi = float(d["efermi"])
    pdos = d.get("pdos")
    if pdos and len(pdos) == natoms:
        orbitals = []
        for site in pdos:
            for name in map(orbital_name, site):
                if name not in orbitals:
                    orbitals.append(name)
        arr = np.zeros((natoms, len(spins), len(orbitals), len(es.dos_energies)))
        for i, site in enumerate(pdos):
            for name, orb in site.items():
                by_spin = orb.get("densities", orb)
                for k, s in enumerate(spins):
                    if s in by_spin:
                        arr[i, k, orbitals.index(orbital_name(name))] = _array(by_spin[s])
        es.pdos, es.orbitals = arr, orbitals
    return _match_spins(es)


def _match_spins(es: ElectronicStructure) -> ElectronicStructure:
    if es.eigenvalues is not None and len(es.eigenvalues) != len(es.dos):
        # bands and DOS from calculations with and without spin: the DOS takes the bands' channels
        if len(es.eigenvalues) == 1:
            es.dos = es.dos.sum(0, keepdims=True)
            es.pdos = None if es.pdos is None else es.pdos.sum(1, keepdims=True)
        else:   # half of the spinless DOS in each channel
            es.dos = np.repeat(es.dos / 2, 2, axis=0)
            es.pdos = None if es.pdos is None else np.repeat(es.pdos / 2, 2, axis=1)
    return es


def charge_density(chg) -> DataCollection:
    """A pymatgen ``Chgcar`` or its dict: "Charge Density" in e/Angstrom^3 (the file's rho*V
    divided by the volume, as EWALD's CHGCAR reader does) and "Magnetization" when spin-polarized."""
    from ewald.data import VoxelGrid

    if isinstance(chg, dict):
        data = structure(chg["poscar"]["structure"])
        grids = chg["data"]
    else:
        data = structure(chg.structure)
        grids = chg.data
    volume = abs(float(np.linalg.det(data.cell.matrix)))
    grid = VoxelGrid(Cell(data.cell.matrix, pbc=True))
    grid["Charge Density"] = _array(grids["total"]) / volume
    if grids.get("diff") is not None:
        grid["Magnetization"] = _array(grids["diff"]) / volume
    data.grids["charge-density"] = grid
    return data


def trajectory(traj: dict) -> list[DataCollection]:
    """An emmet ``RelaxTrajectory`` (as mp-api returns it, a dict): one frame per ionic step
    with ``Force`` and the attribute ``Energy`` (eV) when the task has them."""
    from ase.data import chemical_symbols

    symbols = [chemical_symbols[int(z)] for z in traj["elements"]]
    lattices = traj.get("lattice")
    energies = traj.get("energy") or traj.get("e_wo_entrp")
    forces = traj.get("forces")
    frames = []
    for i, coords in enumerate(traj["cart_coords"]):
        if coords is None:
            continue
        lat = lattices[i] if lattices else lattices
        cell = Cell(np.asarray(lat, float), pbc=True) if lat is not None else Cell(pbc=False)
        data = DataCollection(np.asarray(coords, float).reshape(-1, 3), symbols, cell)
        if forces and forces[i] is not None:
            data.particles["Force"] = np.asarray(forces[i], float)
        if energies and energies[i] is not None:
            data.attributes["Energy"] = float(energies[i])
        data.attributes["Timestep"] = i + 1
        frames.append(data)
    return frames
