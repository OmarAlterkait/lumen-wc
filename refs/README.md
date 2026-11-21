# How each reference product was made

The products of `src/lumen_wc/references.json`, each published as a release asset (`<id>.tar.gz`) and fetched on
first use. Each product's `producer` entry in the manifest records the tool, its commit, image and settings.

| Product | Producer |
|---|---|
| `wcsim-sk-e2dc7a48`, `wcsim-wcte-e2dc7a48`, `wcsim-annie-e88314b`, `wcsim-hk-e2dc7a48`, `wcsim-hk-id-e2dc7a48`, `wcsim-hk-od-e2dc7a48`, `wcsim-iwcd-e2dc7a48` | WCSim runs: `wcsim/build.sh`, `wcsim/run.sh` (hits), the sources in `wcsim/cfg`, reduced by `make_store.sh` |
| `gdml-repaired` | `make_store.sh`: `python -m lumen.gdml.repair` on the SK, WCTE and ANNIE GDMLs of the WCSim products |
| `sk-g4ref-original`, `hk-g4ref-original`, `wcte-g4ref-original`, `annie-g4ref-original` | g4ref on the original GDMLs: their producers' `run` blocks with lumen's `tools/g4ref` (`references.sh --runs`, `make_store.sh --runs`) |
| `sk-g4ref-export`, `hk-g4ref-export`, `wcte-g4ref-export`, `annie-g4ref-export` | g4ref on the overlap-free exports (`python -m lumen.compare.ownership`), the same way |
| `mc-gate-wc-3b241f1` | lumen's `tools/g4ref/mc_store.sh STORE ID lumen_wc ...`: the MC gate's records at lumen 3b241f1 (`python -m lumen.compare gate --package lumen_wc`, each record's environment inside it and in the producer) and the same photon files; the mc checks gate on it |
| `mc-gate-wc-de9e145` | lumen's `tools/g4ref/mc_store.sh STORE ID lumen_wc ...`: the MC gate's records (`python -m lumen.compare.mc gate --package lumen_wc`) and its photon files; superseded by mc-gate-wc-3b241f1 (records before lumen's deposit convention, decision 11: arrivals over A_n) |

The g4ref runs on the original GDMLs (`g4ref-sk`, `g4ref-wcte`, `g4ref-annie`) read the product `gdml-repaired`, which `make_store.sh`
writes from WCSim's exports with `python -m lumen.gdml.repair` (its edits listed in the producer). The stored
`wcte-g4ref-original` and `annie-g4ref-original` carry the same files under earlier names (`wcte_probe.gdml`,
`annie_v2_g4clean.gdml`), byte for byte (sha256 3fb95657... and 4aba633f...).

Fixed inputs, kept as stored (no producer in any repository): the MC gate's photon files (fixed emission rows sampled
once), and `g4ref-events-wc-933e631d` (two Geant4 events of Super-K, a muon and an electron of 600 MeV, the notebooks'
examples).

`g4ref-gun-sk-9fd555c0` (notebook 02's many events: 100 muons and 100 electrons of 600 MeV at random places and
directions in Super-K) is made by `events.sh` (lumen's `tools/g4ref/events.py`; WCSim's hit rule, as the charge
check's references): its manifest entry gives the binary, the region and the flags, and `events.json` every event's
vertex, direction and seed.

## What g4ref changes in Geant4

g4ref (lumen's `tools/g4ref/g4ref.cc`) links Geant4 10.7.4 unmodified (`G4OpticalPhysics`, photons as primaries). Its
stepping action changes two Geant4 10.7 behaviours, both on by default and used by every g4ref product here:

- the photon's speed after a boundary step (`--no-fix-velocity` turns it off): Geant4 10.7 keeps the speed c a photon
  takes on a zero-length step into a volume without RINDEX (and the old medium's speed after a reflection); g4ref sets
  the GROUPVEL of the medium the photon continues in. `tools/g4ref/velocity_after_relocation.patch` (already in
  `g4ref.cc`) extends it to a reflection after which Geant4 relocated the photon into an overlapping sibling that
  contains the point: the photon continues in that sibling's medium. It moves arrival times, not counts;
- a NoRINDEX kill on a step shorter than 1 um out of a volume without RINDEX into one with RINDEX (`--no-revive`):
  g4ref keeps the photon alive in the medium it re-enters. Geant4 10.7 leaves a photon reflected off a
  dielectric_metal surface inside the volume behind it, and its step back is StepTooSmall only within 1e-9 mm (1.4 %
  of WCTE's photons were killed 1e-7 - 2e-4 mm inside a cathode). It moves counts.

## WCSim's tuning file

Each macro names its tuning file (`# tuning:`, read by `wcsim/run.sh`): IWCD its own
(`tuning_parameters_iwcd.mac`), the rest Hyper-K FD's (`tuning_parameters_hkfd.mac`, whose values are
WCSimTuningParameters' defaults); ANNIE's WCSim reads its own. The two files differ only in the three OD
reflectivities, which only a geometry with an OD reads (WCSim e2dc7a48 builds one only in its *WithOD* geometries).
The stored SK, WCTE, Hyper-K (`hk`, `hk_id`) and IWCD products and exports ran with `tuning_parameters_iwcd.mac`
(run.sh's earlier default): none of those geometries has an OD and their exports carry no OD surface, so their
optics are the same under either file. `hk_od` ran with `tuning_parameters_hkfd.mac`.
