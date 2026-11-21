# Hyper-Kamiokande and IWCD

lumen-wc converts Hyper-K's far detector and IWCD from the geometry WCSim e2dc7a4 builds, exported to GDML by WCSim
itself. The GDML ships here (xz-compressed, `src/lumen_wc/gdml/`; `gdml/SOURCES.json` holds each file's WCSim
commit, how it was exported, the export's sha256 and the sha256 of the shipped file, checked when it is converted).
No data directory is read:

```python
import lumen
det = lumen.load(lumen.convert("lumen_wc:hk", out="hk.lumen", data="."))
```

| Name | WCSim geometry (`/WCSim/WCgeom`) | Sensors (WCSim collection: group, value set of `lumen:sensor`) | Readout gate |
|---|---|---|---|
| `hk` | `HyperK` at 20 % coverage: the generic 67.0 x 65.8 m cylinder | 19,620 20-inch Box&Line tubes: `pmt`, `lumen_wc:wcsim_bl20_hqe` | 0-1400 ns |
| `hk_id` | `HyperK_HybridmPMT_IDonly_Realistic`: the inner detector as built | `glassFaceWCPMT`: `bl`, `lumen_wc:wcsim_bl20_hqe`; `glassFaceWCPMT2` (the mPMTs' 3-inch tubes): `mpmt`, `lumen_wc:wcsim_r14374` | 0-1450 ns |
| `hk_od` | `HyperK_HybridmPMT_WithOD_Realistic`: the inner and outer detectors | as `hk_id`, and `glassFaceWCPMT_OD` (the OD's 3-inch tubes with their WLS plates): `od`, `lumen_wc:wcsim_r14374_fdod` | 0-1450 ns |
| `iwcd` | `IWCD_mPMT` | the mPMTs' 3-inch tubes: `pmt`, `lumen_wc:wcsim_r12199_02` | 0-1050 ns |

The recipes are those of the other WCSim detectors (`lumen_wc.wcsim`): a sensor is WCSim's `InteriorWCPMT`, counted
as the photon is absorbed entering it from the glass, and the value set applies the QE after tracking. Hybrids have one
group per WCSim collection (the id map's column `collection`). `hk_od` records G4OpWLS's exponential time profile, as
its WCSim reference ran.

## The GDML

WCSim publishes no GDML file. `refs/wcsim/run.sh DET gdml` builds the geometry with WCSim e2dc7a4 and writes it with
Geant4's GDML writer (`refs/wcsim/patches/wcsim_main_gdml.patch`, built against Geant4 10.7.4), with three changes at
export that leave the geometry as WCSim builds it (`refs/wcsim/patches/wcsim_hk_export.patch`: the mPMTs'
parameterised tubes written as placements, the realistic placement's assemblies written as their placements, and
`HyperK`'s obsolete-geometry exit commented out). Each export's sha256 is that of the GDML in its WCSim charge
reference. Like SK's and WCTE's exports, each writes inf in one surface GROUPVEL table (3 values, read by no Geant4
process), which Geant4 and lumen refuse; the shipped file is the copy `python -m lumen.gdml.repair` writes (those 3
values written 1e30, nothing else changed). WCSim is MIT-licensed.

| File | Export (MB) | Shipped, xz (kB) |
|---|---|---|
| `hk.gdml` | 14.3 | 250 |
| `hk_id.gdml` | 7.1 | 184 |
| `hk_od.gdml` | 8.5 | 227 |
| `iwcd.gdml` | 0.32 | 18 |

## Comparison with WCSim

`python -m lumen.compare charge hk --package lumen_wc --detector-file hk.lumen` compares lumen's detected light per tube with WCSim's
true hits (product `wcsim-hk-e2dc7a48`, every file's sha256 checked against the manifest): isotropic 400 and 350 nm
photons from five points, WCSim run with `DoNotApplyQE`, collection efficiency off and no dark noise
(`refs/wcsim/macros/hk.mac`, `refs/wcsim/cfg/hk.cfg`). `hk_id`, `hk_od` and `iwcd` have their entries
(`wcsim-hk-id-`, `wcsim-hk-od-`, `wcsim-iwcd-e2dc7a48`).

## Open

- `hk_id`, `hk_od` and `iwcd` convert but do not load: their mPMTs' silicone gel (`SilGel`) has ABSLENGTH 0 at its
  end knots (0.1 eV and 7 eV, 12398 nm and 177 nm), outside the light water carries (water's tables start at 200 nm),
  and lumen checks every table at all its knots, refusing a zero length. Geant4 reads the table at the photon's energy,
  where it is positive. They load once lumen checks a table at its knots inside the light's domain.
- A run's device memory. A timed sensor group's histograms take, per tube, its time nodes over the readout gate
  (exact sums, 44 bytes a cell) and a charge cell and its per-photon moment per wavelength and angle bin
  (`lumen.simulate` refuses a run that does not fit, before launch). `hk` needs about 18.4 GB (computed): the time
  histogram is 18.05 GB (19,620 tubes x 20,908 nodes of 0.067 ns over 0-1400 ns) and the charge cells and their
  moment 0.36 GB, over the 10.8 GB a 2080 Ti gives; it needs a device of at least about 20 GB free. The same rule gives (computed,
  not run) `hk_id` 42 GB, `hk_od` 48 GB and `iwcd` 7.4 GB.
