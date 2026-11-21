#!/bin/bash
# Make g4ref-gun-sk-<g4ref>: Geant4 events of Super-K for notebook 02's many-event comparison
# (lumen.compare.event.compare_events), with lumen's tools/g4ref/events.py.
#
#   events.sh OUT                 the table (once), then the runs: a Slurm array task K of N runs its rows
#   sbatch --array 0-9 events.sh OUT
#
# 100 mu- and 100 e- of 600 MeV, vertices uniform in a cylinder 2 m inside the PMTs (radius 14.9 m, |z| < 16.1 m),
# isotropic directions; one Geant4 run per event on the repaired GDML (product gdml-repaired), with the flags of the
# family's g4ref references: Cherenkov and scintillation on, WCSim's hit rule (--wcsim-hits: a hit is what WCSim
# counts, as in the charge check), --split-ev 6.19. Each event file records its vertex, direction, seed and flags.
set -euo pipefail
OUT=$1
EVENTS=${G4REF_TOOLS:?the tools/g4ref directory of lumen}/events.py
G4REF=${G4REF:?the g4ref binary (tools/g4ref/build.sh)}
GDML=${LUMEN_DATA:?the reference store}/gdml-repaired/sk.gdml
PY=${LUMEN_PY:-python3}
if [ ! -f "$OUT/events.json" ]; then
  $PY "$EVENTS" table "$OUT" --name sk --particle mu- --mev 600 --n 100 --seed 11 --region cylinder:z,14.9,-16.1,16.1
  $PY "$EVENTS" table "$OUT" --name sk --particle e- --mev 600 --n 100 --seed 12 --region cylinder:z,14.9,-16.1,16.1
fi
$PY "$EVENTS" run "$OUT" --g4ref "$G4REF" --gdml "$GDML" --sens-regex '^InteriorWCPMT' \
  --task "${SLURM_ARRAY_TASK_ID:-0}" --tasks "${SLURM_ARRAY_TASK_COUNT:-1}" \
  --cherenkov --scintillation --split-ev 6.19 --wcsim-hits
