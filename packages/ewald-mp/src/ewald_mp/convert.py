"""pymatgen and emmet objects from mp-api as EWALD frames."""
from __future__ import annotations

import numpy as np

from ewald import Cell, DataCollection
from ewald.electronic import ElectronicStructure, merge_ticks, path_distances, pretty_label


def structure(s) -> DataCollection:
    """A pymatgen ``Structure`` (no ASE round trip, so site properties stay out of the way)."""
    symbols = [site.specie.symbol if hasattr(site.specie, "symbol") else str(site.specie) for site in s]
    data = DataCollection(np.asarray(s.cart_coords, float).reshape(-1, 3), symbols,
                          Cell(np.asarray(s.lattice.matrix, float), pbc=True))
    magmom = s.site_properties.get("magmom") if hasattr(s, "site_properties") else None
    if magmom is not None and not any(m is None for m in magmom):
        data.particles["Magnetic Moment"] = np.asarray(magmom, float)
    return data


def _spins(obj):
    from pymatgen.electronic_structure.core import Spin

    return [Spin.up] + ([Spin.down] if Spin.down in obj else [])


def bands(bs, es: ElectronicStructure) -> ElectronicStructure:
    """Fill ``es`` with a pymatgen ``BandStructure(SymmLine)``: eigenvalues, the path, its labels."""
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


def dos(d, es: ElectronicStructure, natoms: int) -> ElectronicStructure:
    """Fill ``es`` with a pymatgen ``Dos``/``CompleteDos``: the total DOS and, for a complete
    one, the projected DOS per site and orbital (VASP's lm names)."""
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
                name = getattr(orb, "name", str(orb))
                if name not in orbitals:
                    orbitals.append(name)
        arr = np.zeros((natoms, len(spins), len(orbitals), len(es.dos_energies)))
        for i, site in enumerate(sites):
            for orb, by_spin in pdos.get(site, {}).items():
                j = orbitals.index(getattr(orb, "name", str(orb)))
                for k, s in enumerate(spins):
                    if s in by_spin:
                        arr[i, k, j] = by_spin[s]
        es.pdos, es.orbitals = arr, orbitals
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
    """A pymatgen ``Chgcar``: "Charge Density" in e/Angstrom^3 (the file's rho*V divided by the
    volume, as EWALD's CHGCAR reader does) and "Magnetization" when spin-polarized."""
    from ewald.data import VoxelGrid

    data = structure(chg.structure)
    volume = float(chg.structure.volume)
    grid = VoxelGrid(Cell(data.cell.matrix, pbc=True))
    grid["Charge Density"] = np.asarray(chg.data["total"], float) / volume
    if chg.data.get("diff") is not None:
        grid["Magnetization"] = np.asarray(chg.data["diff"], float) / volume
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
