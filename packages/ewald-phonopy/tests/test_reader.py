import numpy as np
import pytest

phonopy = pytest.importorskip("phonopy")
pytest.importorskip("seekpath")


def _same_eigenspaces(a, b, tol=1e-3):
    """Eigenvectors agree up to a rotation inside each degenerate subspace (a basis there is
    arbitrary): compare the projectors onto the subspaces of equal frequency."""
    for q in range(a.num_qpoints):
        f = a.frequencies[q]
        groups, start = [], 0
        for i in range(1, len(f) + 1):
            if i == len(f) or abs(f[i] - f[start]) > tol:
                groups.append(range(start, i))
                start = i
        for g in groups:
            va = a.eigenvectors[q, list(g)].reshape(len(g), -1)
            vb = b.eigenvectors[q, list(g)].reshape(len(g), -1)
            np.testing.assert_allclose(va.T @ va.conj(), vb.T @ vb.conj(), atol=1e-4)


@pytest.fixture
def cu_params(tmp_path, monkeypatch):
    """Cu (EMT) phonopy_params.yaml with forces, and the band.yaml phonopy writes for it."""
    from ase import Atoms
    from ase.build import bulk
    from ase.calculators.emt import EMT
    from phonopy.structure.atoms import PhonopyAtoms

    monkeypatch.setenv("EWALD_CONFIG_DIR", str(tmp_path / "config"))
    a = bulk("Cu", "fcc", a=3.6, cubic=True)
    unit = PhonopyAtoms(symbols=a.get_chemical_symbols(), cell=a.cell[:], scaled_positions=a.get_scaled_positions())
    ph = phonopy.Phonopy(unit, supercell_matrix=np.eye(3) * 2, primitive_matrix="auto")
    ph.generate_displacements(distance=0.01)
    forces = []
    for sc in ph.supercells_with_displacements:
        atoms = Atoms(sc.symbols, cell=sc.cell, scaled_positions=sc.scaled_positions, pbc=True)
        atoms.calc = EMT()
        forces.append(atoms.get_forces())
    ph.forces = np.array(forces)
    path = tmp_path / "phonopy_params.yaml"
    ph.save(path, settings={"force_sets": True, "displacements": True})
    ph.produce_force_constants()
    ph.auto_band_structure(npoints=51, with_eigenvectors=True, write_yaml=True, filename=str(tmp_path / "band.yaml"))
    return path, tmp_path / "band.yaml"


def test_sniff(cu_params):
    from ewald_phonopy.reader import sniff

    params, band = cu_params
    assert sniff(params) and not sniff(band)


def test_reader_matches_phonopy_band_yaml(cu_params):
    from ewald import import_file, plugins
    from ewald_phonopy.reader import PhononReader
    params, band = cu_params
    pipe = import_file(params)
    assert plugins.find_reader(params).name == "phonopy-fc"
    ours = pipe.compute(0).attributes["Phonon Modes"]
    ref = PhononReader(band).modes            # ewald's own band.yaml reader
    assert ours.frequencies.shape == ref.frequencies.shape
    np.testing.assert_allclose(ours.frequencies, ref.frequencies, atol=1e-4)
    np.testing.assert_allclose(ours.qpoints, ref.qpoints, atol=1e-6)
    np.testing.assert_allclose(ours.distances, ref.distances, atol=1e-5)
    _same_eigenspaces(ours, ref)
    assert abs(ours.frequencies[0, :3]).max() < 0.05          # acoustic modes vanish at Gamma
    np.testing.assert_allclose([t[0] for t in ours.ticks], [t[0] for t in ref.ticks], atol=1e-5)
    # the mode animates
    from ewald.modifiers import PhononMode

    pipe.modifiers.append(PhononMode(qpoint=len(ours.qpoints) // 2, band=2))
    d = pipe.compute(3)
    assert d.count >= 1 and np.isfinite(d.positions).all()


def test_from_phonopy_object(cu_params):
    import phonopy

    from ewald_phonopy import from_phonopy

    params, band = cu_params
    ph = phonopy.load(params, log_level=0)
    pipe = from_phonopy(ph, frames=8)
    assert pipe.source.num_frames == 8 and [type(m).__name__ for m in pipe.modifiers] == ["PhononMode"]
    data = pipe.compute(2)
    assert "Phonon Mode" in data.vectors and "Phonon.Frequency" in data.attributes
    custom = from_phonopy(ph, band_path=[[[0, 0, 0], [0.5, 0, 0.5]]], labels=["G", "X"], npoints=11, mode=False)
    modes = custom.compute(0).attributes["Phonon Modes"]
    assert modes.frequencies.shape == (11, 3) and [t[1] for t in modes.ticks] == ["G", "X"]
    with pytest.raises(ValueError, match="force constants"):
        from_phonopy(phonopy.Phonopy(ph.unitcell, supercell_matrix=np.eye(3) * 2))


def test_ticks_across_a_break_in_the_path():
    from ewald_phonopy.reader import _ticks

    d = [np.linspace(0, 1, 3), np.linspace(1, 2, 3), np.linspace(2, 3, 3)]
    labels = ["G", "X", "W", "K", "G"]                      # phonopy: G-X-W | K-G
    assert _ticks(d, [True, False, False], labels) == [(0, "G"), (1, "X"), (2, "W|K"), (3, "G")]
    assert _ticks(d, None, ["G", "X", "L", "G"]) == [(0, "G"), (1, "X"), (2, "L"), (3, "G")]
