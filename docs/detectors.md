# The WCSim detectors

lumen-wc holds the recipes (`lumen_wc.wcsim`) and PMT value sets of seven WCSim detectors. Convert one once from its
GDML and load its file:

```python
import os
from pathlib import Path

import lumen
from lumen.compare import references

data = references.store()             # the reference data directory: LUMEN_DATA, else lumen's cache (below)
out = Path(os.environ.get("LUMEN_EXAMPLES_OUT", "lumen-examples"))
path = lumen.convert("lumen_wc:iwcd", out=out / "iwcd.lumen", data=data, overwrite=True)   # once
det = lumen.load(path)
print(len(det.params()), "parameters;", len(det.sensor_table().name), "sensors")
```

| Name | Detector | Sensors | PMT values (sensor model `lumen:sensor`) |
|---|---|---|---|
| `sk` | Super-Kamiokande (WCSim's geometry) | 20-inch PMTs | `lumen_wc:sk_r3600` |
| `wcte` | the Water Cherenkov Test Experiment (WCSim) | 3-inch PMTs | `lumen_wc:wcte_r14374` |
| `hk` | Hyper-K's generic far-detector cylinder ([hyperk.md](hyperk.md)) (WCSim's `HyperK`, 20 % coverage) | 20-inch Box&Line PMTs | `lumen_wc:wcsim_bl20_hqe` |
| `hk_id` | Hyper-K's far-detector inner detector as built (WCSim's `HyperK_HybridmPMT_IDonly_Realistic`) | 20-inch Box&Line PMTs and mPMTs of 3-inch PMTs, one group per WCSim collection (the id map's column `collection`): `bl` (19,746), `mpmt` (15,504) | `lumen_wc:wcsim_bl20_hqe`, `lumen_wc:wcsim_r14374` |
| `hk_od` | Hyper-K's far detector with its outer detector (WCSim's `HyperK_HybridmPMT_WithOD_Realistic`) | as `hk_id`, and the outer detector's 3-inch PMTs with their wavelength-shifting plates, group `od` (3,568) | as `hk_id`, and `lumen_wc:wcsim_r14374_fdod` |
| `iwcd` | the Intermediate Water Cherenkov Detector (WCSim's `IWCD_mPMT`) | mPMTs of 3-inch PMTs | `lumen_wc:wcsim_r12199_02` |
| `annie` | ANNIE (ANNIE's WCSim) | its PMT types (LAPPDs are not sensors: below) | one group per tank tube type, each with its own value set (`lumen_wc:wcsim_annie_R7081`, `_D784KFLB`, `_R5912HQE`, `_R7081HQE`) |

Every detector has hits on each modelled group (its value sets have the electronics). Hits and waveforms read the light
inside each group's readout gate (ns after emission), computed at conversion by one rule (`lumen_wc.wcsim.readout_gate`):
WCSim's 950 ns after its trigger, plus the light's crossing of the detector volume (its longest chord at 4.6 ns/m),
rounded up to 50 ns. That gives SK 0 to 1200 ns (WCSim's water volume, 35.8 x 36.2 m), WCTE and ANNIE 0 to 1000 ns,
IWCD 0 to 1050 ns, `hk` 0 to 1400 ns, `hk_id` and `hk_od` 0 to 1450 ns. `lumen.simulate(..., gate=(start, end))`
overrides it for a run.

ANNIE's sensor set reads its PMTs only. LAPPDs need a sensor model of their own, which lumen does not have, so light
that enters an LAPPD is never detected, and the derivative with respect to the LAPPD glass's TRANSMITTANCE
(`surfaces/GlassCathodeSurface/TRANSMITTANCE`) is exactly 0: more transmission only sends light where nothing counts
it. The gradient check reports this parameter as "zero"; this is correct for this sensor set, not a bug.

## Where the GDML comes from

SK's, WCTE's and ANNIE's GDML are not in the repository: `lumen_wc.DETECTORS` names each one's path in the reference
data directory (`references.store()`: `LUMEN_DATA`, else `data` under lumen's cache root): `gdml-repaired/sk.gdml`,
`gdml-repaired/wcte.gdml`, `gdml-repaired/annie_v2.gdml` (the copies `python -m lumen.gdml.repair` writes of WCSim's
exports, which Geant4 refuses as written). A conversion that finds them missing fetches the product `gdml-repaired`
(64 MB, this repository's release asset) and checks its sha256. Hyper-K's and IWCD's
ship in the package, the repaired copies of WCSim e2dc7a4's own exports, xz-compressed with their provenance and sha256
(`src/lumen_wc/gdml/`): see [hyperk.md](hyperk.md). Each comes from WCSim (ANNIE's from ANNIE's WCSim).

What each recipe decides, and why, is in the module docstring of `lumen_wc.wcsim`. The value sets are written by
`tools/transcribe.py` from WCSim's sources (WCSim e2dc7a4, ANNIE's WCSim e88314b). Every number is parsed from its source and cites its file and line (`provenance.fields`); a number lumen needs that
no source gives (fit ranges, the charge histogram's grid, an efficiency or gain of 1) is a stated choice with its
reason (`provenance.choices`), and the tests check that every field is one or the other. The validation report is
regenerated after a change to the value sets or the recipes.

## Validation summary (0.2.0)

From the records in [validation-report.md](validation-report.md) (`python -m lumen.compare charge|gradients`, lumen
3b241f1 with tallymap cba41b6 and jax 0.6.2, RTX 2080 Ti, 2026-11-20). Total charge, lumen over the reference, with both
Monte Carlo errors; the g4ref rows gate (|z| ≤ 3), the WCSim rows gate only where the detector has no g4ref reference
(the Hyper-K ID and OD, IWCD).

| detector | against Geant4 10.7.4 (g4ref, export) | against WCSim | Geant4 export / original |
|---|---|---|---|
| Super-K | 1.0001 ± 0.0006 | 0.9991 ± 0.0006 | 0.9994 ± 0.0008 |
| WCTE | 0.9996 ± 0.0007 | 0.9999 ± 0.0007 | 1.0008 ± 0.0009 |
| ANNIE | 0.9991 ± 0.0008 | 1.0760 ± 0.0014 (below) | 1.0008 ± 0.0010 |
| Hyper-K | 0.9994 ± 0.0006 | 0.9989 ± 0.0006 | 1.0000 ± 0.0007 |
| Hyper-K ID |  | 1.0002 ± 0.0005 |  |
| Hyper-K OD |  | 0.9990 ± 0.0015 |  |
| IWCD |  | 1.0000 ± 0.0007 |  |

Every gated charge row passes (105 of 105, per-sensor agreement included). Gradient gates (16 seeds of 32,768 photons;
the production comparison on 64 seeds): ANNIE 24 of 24, Super-K 8 of 8, WCTE 19 of 19 gated parameter families pass; 8,
5 and 15 more are reported, not gated. Super-K's reverse-mode row (jax.grad of a fixed weighting of the arrivals against
fixed-reference finite differences, lumen 96f0633 with tallymap a7d93d4): largest ratio 0.042, 10 of 10 tested families
agree; the other detectors have no reverse-mode row.

**ANNIE against WCSim.** ANNIE's WCSim runs on Geant4 10.1.3, which loses 7 to 8 % of the light reflected off the
inner-structure frame where g4ref and lumen agree (a navigation difference of that Geant4 build, measured with a minimal
Geant4 application). lumen's charge is 1.076 times WCSim's there; against Geant4 10.7.4 on the same GDML it is 0.9991 ±
0.0008. No reference is scaled to agree, so the WCSim row is reported, not gated.

## Comparisons

`python -m lumen.compare charge|geometry|gradients NAME --package lumen_wc --detector-file NAME.lumen` runs lumen's
checks (`lumen.compare`) with this package's reference manifest (`src/lumen_wc/references.json`); the records make `docs/validation-report.md`
(`python -m lumen.compare report`); the reference products are fetched on first use (`refs/README.md` says how each was
made). These, and the gradient gates on 64 seeds, need a GPU and run before a release, not in CI.
