"""EWALD plugin: phonon bands from phonopy's input with forces or force constants.

Reader ``phonopy-fc``: ``phonopy.yaml``, ``phonopy_params.yaml`` or ``phonopy_disp.yaml`` with
``FORCE_SETS`` / ``FORCE_CONSTANTS``; phonopy computes the band structure with eigenvectors
along the seekpath path. ``from_phonopy(phonon)`` turns a ``phonopy.Phonopy`` with force
constants (for example from aiida-phonopy) into a pipeline playing a mode.

Everything that needs no phonopy (band.yaml / mesh.yaml / qpoints.yaml, VASP OUTCARs of
IBRION=5-8 runs, ``PhononModes`` and the ``PhononMode`` animation) is part of EWALD itself since
2026-10-23 (``ewald.phonon``, ``ewald.io.phonon``, ``ewald.modifiers.PhononMode``); this package
re-exports those names so code written against ewald-phonopy 0.2 keeps working.
"""
from pathlib import Path

try:
    from ewald.io.phonon import PhononReader, PhonopyYamlReader, VaspPhononReader
except ImportError as exc:   # an EWALD from before phonons moved back into it
    raise ImportError("ewald-phonopy 0.3 needs an EWALD with built-in phonon modes (from 2026-10-23): "
                      "update EWALD, or install ewald-phonopy 0.2.2") from exc
from ewald.modifiers.phonon import PhononMode
from ewald.phonon import PhononModes, read_modes, read_outcar_modes, read_phonopy_yaml

from .reader import PhonopyForceConstantsReader, from_phonopy, modes_from_phonopy, reader_from_phonopy

#: Example files that ship with the plugin (``Cu3Au_band.yaml``: L1_2 Cu3Au bands with eigenvectors).
EXAMPLES = Path(__file__).parent / "examples"

__all__ = ["PhononMode", "PhononModes", "PhononReader", "PhonopyYamlReader", "VaspPhononReader",
           "PhonopyForceConstantsReader", "modes_from_phonopy", "from_phonopy", "reader_from_phonopy", "read_modes",
           "read_outcar_modes", "read_phonopy_yaml", "EXAMPLES"]
