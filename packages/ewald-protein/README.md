# ewald-protein (proof of concept)

Proteins in EWALD: PDB/mmCIF with residues and chains (gemmi), helix/strand/coil from backbone
hydrogen bonds (simplified DSSP), and a cartoon drawn as one `SurfaceMesh`, so the OpenGL view,
the ray tracer and SVG/PDF output show the same picture.

```python
from ewald import load, view
from ewald_protein import SecondaryStructure

pipe = load("adk.pdb")
pipe.add(SecondaryStructure())
view(pipe, visuals=[{"name": "Cartoon", "params": {"color_by": "rainbow"}}], show_atoms=False)
```

Status: proof of concept, not in the plugin index, no tests yet. Not done: 3-10/pi helices,
bulges, insertion codes, ligands and nucleic acids, picking a residue on the cartoon, a GUI form.
