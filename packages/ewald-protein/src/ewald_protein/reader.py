"""PDB / mmCIF / mmJSON via gemmi, keeping what a protein needs: residues, chains, atom names."""
from __future__ import annotations

import os

import numpy as np

from ewald.data import Cell, DataCollection
from ewald.io.base import FrameReader

_PDB = (".pdb", ".ent", ".pdb1")
_CIF = (".cif", ".mmcif")


def sniff(path: str) -> bool:
    """PDB files by name; a .cif only when it is a macromolecular one (``_atom_site.group_PDB``),
    so crystallographic CIFs stay with the built-in reader."""
    name = os.path.basename(str(path)).lower()
    if name.endswith(".gz"):
        name = name[:-3]
    if name.endswith(_PDB) or name.endswith(".mmcif"):
        return True
    if name.endswith(".cif"):
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(200_000)
        return "_atom_site.group_PDB" in head
    return False


class ProteinReader(FrameReader):
    """PDB and mmCIF files through gemmi: one frame per model, with the per-atom properties
    'Atom Name', 'Residue Name', 'Residue Index' (sequence number), 'Chain' and 'Polymer'
    (1 for amino-acid residues) besides 'Position' and 'Particle Type' (element). Helix and
    sheet records of the file go into ``attributes["Protein"]``."""

    description = "Proteins (PDB, mmCIF) with residues and chains via gemmi"
    sniff = staticmethod(sniff)
    priority = 20

    def __init__(self, path, remove_water: bool = True):
        import gemmi

        self.path = str(path)
        self.remove_water = remove_water
        st = gemmi.read_structure(self.path)
        st.setup_entities()
        if remove_water:
            st.remove_waters()
        st.remove_hydrogens()
        self._st = st
        self._frames: dict[int, DataCollection] = {}

    def __len__(self) -> int:
        return len(self._st)

    def read(self, index: int) -> DataCollection:
        if index not in self._frames:
            self._frames[index] = self._convert(index)
        return self._frames[index]

    def _convert(self, index: int) -> DataCollection:
        import gemmi

        model = self._st[index]
        pos, elem, aname, rname, rseq, chain, poly = [], [], [], [], [], [], []
        for ch in model:
            for res in ch:
                amino = gemmi.find_tabulated_residue(res.name)
                is_aa = bool(amino and amino.is_amino_acid())
                for at in res:
                    if at.altloc not in ("\0", "A"):
                        continue
                    pos.append(at.pos.tolist())
                    # PDB files without element columns (MD tools) get wrong guesses such as
                    # Ca for CA or Hg for HG: in amino acids the name's first letter is the element
                    elem.append(at.name.lstrip("0123456789")[:1] if is_aa else at.element.name)
                    aname.append(at.name)
                    rname.append(res.name)
                    rseq.append(res.seqid.num)
                    chain.append(ch.name)
                    poly.append(is_aa)
        pos = np.asarray(pos, float).reshape(-1, 3)
        lo, hi = (pos.min(0), pos.max(0)) if len(pos) else (np.zeros(3), np.zeros(3))
        data = DataCollection(pos, elem, Cell(np.diag(hi - lo + 2.0), lo - 1.0, pbc=False))
        data.particles["Atom Name"] = np.asarray(aname).astype(str)
        data.particles["Residue Name"] = np.asarray(rname).astype(str)
        data.particles["Residue Index"] = np.asarray(rseq, np.int64)
        data.particles["Chain"] = np.asarray(chain).astype(str)
        data.particles["Polymer"] = np.asarray(poly, np.int8)
        data.attributes["Protein"] = {
            "name": self._st.name,
            "helices": [(h.start.chain_name, h.start.res_id.seqid.num, h.end.res_id.seqid.num)
                        for h in self._st.helices],
            "strands": [(s.start.chain_name, s.start.res_id.seqid.num, s.end.res_id.seqid.num)
                        for sh in self._st.sheets for s in sh.strands],
        }
        data.attributes["SourceFrame"] = index
        return data
