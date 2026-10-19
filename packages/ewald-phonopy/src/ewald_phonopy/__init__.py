"""EWALD plugin: phonon modes.

Readers: phonopy band.yaml / mesh.yaml / qpoints.yaml with eigenvectors (``phonopy``), VASP
OUTCARs of IBRION=5-8 runs (``vasp-phonon``), and phonopy's input with forces or force
constants (``phonopy-fc``: ``phonopy.yaml``, ``phonopy_params.yaml`` or ``phonopy_disp.yaml``
with ``FORCE_SETS`` / ``FORCE_CONSTANTS``), for which phonopy computes the band structure with
eigenvectors along the seekpath path. Modifier: ``PhononMode`` animates one mode (frame ``f`` of
``N`` is phase ``2 pi f / N``), with the mode pattern as arrows.

Once installed, ``import_file("band.yaml")`` and ``from ewald.modifiers import PhononMode`` work
as before this support moved out of ewald's core. The GUI draws the "Phonon Bands" table as a
band structure (click a band to play that mode) and opens phonon files playing a mode.
"""
from pathlib import Path

from .modifier import PhononMode
from .phonon import PhononModes, read_modes, read_outcar_modes, read_phonopy_yaml
from .reader import (PhononReader, PhonopyForceConstantsReader, PhonopyYamlReader, VaspPhononReader,
                     modes_from_phonopy)

#: Example files that ship with the plugin (``Cu3Au_band.yaml``: L1_2 Cu3Au bands with eigenvectors).
EXAMPLES = Path(__file__).parent / "examples"

__all__ = ["PhononMode", "PhononModes", "PhononReader", "PhonopyYamlReader", "VaspPhononReader",
           "PhonopyForceConstantsReader", "modes_from_phonopy", "read_modes", "read_outcar_modes",
           "read_phonopy_yaml", "EXAMPLES"]
