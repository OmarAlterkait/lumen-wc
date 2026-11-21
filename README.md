# lumen-wc

lumen for water Cherenkov detectors (WCSim: Super-K, WCTE, ANNIE, Hyper-K, IWCD).

Owns: WCSim recipes (sensor groups, detector volume, inputs), WCSim PMT sensor data with provenance, repaired-GDML manifests, reference numbers and the comparisons with WCSim and Geant4, built on lumen.compare.

## Install

```bash
pip install "lumen-wc[notebooks] @ git+https://github.com/OmarAlterkait/lumen-wc.git@v0.2.0"
```

This installs lumen 0.2.0 from its repository (lumen is not on PyPI; `pip install lumen` installs an unrelated
package). For a GPU, install lumen's `cuda` extra too and follow [Installing
lumen](https://github.com/OmarAlterkait/lumen/blob/v0.2.0/docs/howto/install.md) (the CUDA 12 driver, the caches).
The reference data (the GDMLs this package does not ship, Geant4 and the experiments' reference runs) is fetched on
first use from this repository's release assets into `LUMEN_DATA`, or `data` under lumen's cache root
(`LUMEN_CACHE`) when it is unset, and checked by sha256. `LUMEN_ASSETS` names a mirror of the release assets
(a base URL, `file://` too) to fetch them from instead.

## Start here

Five notebooks in `notebooks/`, with Super-K as the running example. They need a GPU (3 to 13 minutes each on an
RTX 2080 Ti) and the `notebooks` extra (above). They fetch the reference data they read on first use: the repaired GDMLs
of Super-K, WCTE and ANNIE (3 MB download) and two Geant4 events (1 MB); notebook 02 also the WCSim and Geant4
references of Super-K and WCTE (about 100 MB) and its many Geant4 events (150 MB). All of this repository's
reference products together are 390 MB.
`LUMEN_NOTEBOOKS` names where the notebooks put the converted detector (default `./lumen-notebooks`).

| Notebook | What it shows |
|---|---|
| [`00_quickstart`](notebooks/00_quickstart.ipynb) | a muon and an electron from Geant4 steps, simulated: charge and time per sensor, event displays |
| [`01_convert`](notebooks/01_convert.ipynb) | the GDML and the recipe to a detector file; the geometry and overlap checks; what the file holds |
| [`02_compare_geant4`](notebooks/02_compare_geant4.ipynb) | the same steps through lumen and Geant4 and WCSim; the family's charge check |
| [`03_gradients`](notebooks/03_gradients.ipynb) | what a derivative of a run is; forward mode against finite differences; the Cramér-Rao bound; a 2D loss landscape |
| [`04_calibrate`](notebooks/04_calibrate.ipynb) | three optical parameters fitted by gradient steps and by Fisher scoring; their uncertainty, a profile scan, coverage over toys |

`pytest tests/test_notebooks.py` runs them all end to end (skipped without a GPU).

| Path | What |
|---|---|
| `src/lumen_wc/wcsim.py` | the recipes; `lumen_wc.DETECTORS` names each one's GDML, `lumen.convert("lumen_wc:NAME", out=..., data=...)` converts it |
| `src/lumen_wc/gdml/`, `inputs.py` | Hyper-K's and IWCD's GDML from WCSim, xz with provenance and sha256 (`docs/hyperk.md`), decompressed and checked at conversion (`lumen_wc.prepare`: lumen's one input pipeline, `lumen.inputs.package`) |
| `src/lumen_wc/sensor_values/` | the PMT value sets, `lumen_wc:<set>` (written by `tools/transcribe.py`) |
| `src/lumen_wc/references.json` | the reference manifest of the comparisons (`python -m lumen.compare charge|geometry|gradients NAME --package lumen_wc`) |
| `docs/detectors.md`, `docs/hyperk.md`, `docs/validation-report.md` | the detectors; Hyper-K and IWCD; the comparisons' report |
| `refs/` | how every reference product was made (`README.md`): `make_store.sh` (the g4ref runs: the manifest's producers' `run` blocks, with lumen's `tools/g4ref`), `wcsim/` (WCSim's builds, patches, macros, sources and run harness) |
| `notebooks/` | the user notebooks (Start here, above) |
| `tests/` | the recipes', value sets' and references' tests (`pytest`) |

What runs where: `pytest` here needs no GPU except the notebooks. The MC gate (`python -m lumen.compare gate
--package lumen_wc [NAME ...]`: converted with the recipes, bitwise against the manifest's reference records), the gradient gates on
64 seeds and the comparisons with WCSim and Geant4 need a GPU; they run on a GPU host before a release, not on GitHub.
