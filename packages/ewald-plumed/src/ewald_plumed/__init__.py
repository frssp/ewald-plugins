"""EWALD plugin: PLUMED collective variables.

Modifiers: ``Plumed`` runs a plumed.dat over the trajectory through PLUMED's MD-engine interface
(needs the ``plumed`` Python binding and the PLUMED library, e.g. from conda-forge or a build with
``PLUMED_KERNEL`` set), ``LoadColvar`` puts an existing COLVAR file next to the frames, and
``FreeEnergySurface`` sums a metadynamics HILLS file into a free energy surface (no PLUMED library
needed). :mod:`ewald_plumed.plumed` has the engine (``run``), COLVAR/HILLS/FES parsing,
``fes_from_hills`` (the kernels of ``plumed sum_hills``) and ``plot_fes``. Claude tools:
``compute_plumed_cvs`` and ``read_plumed_output``.

Once installed, ``from ewald.modifiers import Plumed`` and ``import ewald.plumed`` work as before
this support moved out of ewald's core.
"""
from . import plumed
from .modifiers import FreeEnergySurface, LoadColvar, Plumed

__all__ = ["Plumed", "LoadColvar", "FreeEnergySurface", "plumed"]
