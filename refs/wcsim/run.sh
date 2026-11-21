#!/bin/bash
# WCSim as a photon-transport reference. Two modes (environments below):
# EXPORT_BUILD / HITS_BUILD name the builds (default $WCSIM_HOME/build_main/install / build_hk/install; refs/wcsim/build.sh);
# DARK_ELEMENTS the dark-noise elements set to 0 (default "tank"; hybrids "tank tankPMT2", with OD "... OD").
#   run.sh DET gdml OUT.gdml                     the geometry WCSim builds, with its optics, as GDML (lumen loads it)
#   run.sh DET hits CONFIG OUTDIR [NCHUNKS]      (sbatch --array 0-(NCHUNKS-1) --wrap "bash <abs path>/run.sh ...":
#                                                sbatch SCRIPT runs a spool copy, without macros/) isotropic monochromatic photons at
#                                                t = 0 from CONFIG's sources (x y z N E_eV, mm, as g4ref), BATCH per
#                                                event; chunk k runs events k, k + NCHUNKS, ... of every source, then
#                                                dump_hits.C reads WCSim's ROOT file, to_hits.py writes
#                                                chunk<k>_hits.npy / chunk<k>_sensors.csv
# DET: a macro in refs/wcsim/macros (sk, wcte, annie, hk, hkid, hkod, iwcd). Seed SEED + chunk. ANNIE_BUILD: another ANNIE build directory
# (a variant's tuning: a directory of links to build_annie_ref with its own macros/, e.g. build_annie_teflon0).
# Environments (WCSIM_HOME: images/, the builds, src_annie_ref; BIND: the singularity bind paths of your site):
#   hits  WCSim/WCSim develop (unpatched) in the collaboration's image ghcr.io/hyperk/hk-software:main (Geant4
#         10.3.3, ROOT 6.26: WCSim's supported setup)
#   gdml  the same WCSim commit + wcsim_main_gdml.patch (a G4GDMLParser for /persistency/gdml/write) built against
#         Geant4 10.7.4 with GDML (DEVELOP_IMAGE): hk-software's Geant4 has no GDML. Only the geometry is constructed
#         (no tracking), so the export is WCSim's geometry and optics
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DET=$1; MODE=$2
R=${WCSIM_HOME:?the WCSim directory: images/ (hk-software_main.sif, anniesoft_wcsim_latest.sif), the builds, src_annie_ref}
DEV=${DEVELOP_IMAGE:?the image with Geant4 10.7.4 and ROOT 6.26 the GDML exports are built in}
B=${BIND:+-B $BIND}
# the tuning file: the one the macro names on its "# tuning:" line (WCSim's own file for the experiment: IWCD's for
# IWCD, HK FD's for Hyper-K; SK and WCTE have none in WCSim, and HK FD's values off the OD are WCSimTuningParameters'
# defaults, so they take it). tuning_parameters_iwcd.mac differs from it only in the three OD reflectivities, which
# only a geometry with an OD reads (isODConstructed: the *WithOD* geometries)
TUNE=$(sed -n 's/^# tuning: \(macros\/[^ ]*\.mac\).*/\1/p' "$HERE/macros/$DET.mac")
[ -n "$TUNE" ] || [ "$DET" = annie ] || { echo "run.sh: macros/$DET.mac names no tuning file (# tuning: ...)"; exit 1; }
BATCH=${BATCH:-1000}; SEED=${SEED:-20261101}
# the hits block's response settings (ANNIE: in macros/annie.mac, its WCSim has no DoNotApplyQE)
OPTS="/WCSim/PMTQEMethod DoNotApplyQE
/WCSim/PMTCollEff off
/DAQ/Digitizer SKI
/DAQ/Trigger NoTrigger"
for el in ${DARK_ELEMENTS:-tank}; do OPTS="$OPTS
/DarkRate/SetDetectorElement $el
/DarkRate/SetDarkRate 0 kHz"; done
IO="/WCSimIO/WriteDefaultRootFile true
/WCSimIO/WriteFlatRootFile false"
if [ "$DET" = annie ]; then     # ANNIE's image (Geant4 10.1.3, with GDML): one build, the GDML patch included, run in
  IMG=$R/images/anniesoft_wcsim_latest.sif; WCSIM=${ANNIE_BUILD:-$R/build_annie_ref}; ENV="source \${ANNIE_SOURCEME:?anniesoft image: the sourceme of its WCSim checkout}"   # its build dir
  EXE=./WCSim; TUNE=""; OPTS=""; IO=""; LIB=$WCSIM; INC=$R/src_annie_ref/include   # (one ROOT file format only)
  # its Gd capture model opens "../WCSim/cont_dat/*.root" relative to the run directory (GdNeutronHPCaptureFSANNRI.hh,
  # the image's own layout): ../WCSim from $WCSIM is $R/WCSim, a link to the source tree
  [ -e "$R/WCSim" ] || ln -s src_annie_ref "$R/WCSim"
elif [ "$MODE" = gdml ] || [ "${BUILD:-hk}" = main ]; then   # BUILD=main: hits from the exporting build (10.7.4)
  IMG=$DEV; WCSIM=${EXPORT_BUILD:-$R/build_main/install}; EXE=./bin/WCSim
  ENV="source /app/root/bin/thisroot.sh; source \$(geant4-config --prefix)/bin/geant4.sh"
else
  IMG=$R/images/hk-software_main.sif; WCSIM=${HITS_BUILD:-$R/build_hk/install}; ENV="source $HERE/env_hk.sh"; EXE=./bin/WCSim
fi
LIB=${LIB:-$WCSIM/lib}; INC=${INC:-$WCSIM/include/WCSim}
run_wcsim() {   # run_wcsim MACRO LOG
  local try
  for try in 1 2 3; do
    singularity exec $B $IMG bash -c "set -e; $ENV; export WCSIM_BUILD_DIR=$WCSIM; cd $WCSIM; \
      $EXE $1 $TUNE" > "$2" 2>&1 < /dev/null && return 0
    # ANNIE's WCSim writes and reads its git hash in the shared build / source directories (WCSimRootOptions): array
    # tasks starting together can read it empty and assert. Retried (it fails at initialisation, before any event)
    grep -q "Unable to read WCSim commit hash" "$2" || break
    sleep $(( 5 + RANDOM % 20 ))
  done
  # ANNIE's Geant4 10.1.3 crashes in its teardown (G4HadronicProcessStore's destructor), after a completed batch:
  # accepted only when the batch ran to its end and the teardown began
  if [ "$DET" = annie ] && ! grep -q "Batch is interrupted" "$2" && grep -q "Graphics systems deleted" "$2"; then
    echo "run.sh: WCSim crashed in its teardown after a completed batch (accepted): $2"; return 0
  fi
  tail -30 "$2"; exit 1
}
tmp=$(mktemp -d "${TMPDIR:-/tmp}/wcsim_XXXXXX")
if [ "$MODE" = gdml ]; then
  OUT=$3; rm -f "$OUT"
  { cat "$HERE/macros/$DET.mac"; echo "/persistency/gdml/write $OUT"; } > $tmp/g.mac
  run_wcsim $tmp/g.mac "${OUT%.gdml}_wcsim.log"
  ls -la "$OUT"
  exit 0
fi
CFG=$3; OUT=$4; N=${5:-1}; K=${SLURM_ARRAY_TASK_ID:-0}
mkdir -p "$OUT"
awk '!/^[[:space:]]*#/ && NF {if ($4 % '"$BATCH"') {print "N not a multiple of BATCH: " $0; exit 1}}' "$CFG"
s=0
grep -v '^\s*#' "$CFG" | grep -v '^\s*$' | while read -r x y z n e; do
  nev_all=$(( (n + BATCH - 1) / BATCH ))
  nev=$(( (nev_all - K + N - 1) / N ))           # events k, k + N, ... of this source
  if [ "$nev" -gt 0 ]; then
    m=$tmp/s$s.mac
    { cat "$HERE/macros/$DET.mac"
      cat <<EOF
$OPTS
/WCSim/random/seed $(( SEED + 1000 * s + K ))
/mygen/generator gps
/gps/particle opticalphoton
/gps/energy $e eV
/gps/pos/type Point
/gps/pos/centre $x $y $z mm
/gps/ang/type iso
/gps/time 0 ns
/gps/number $BATCH
$IO
/WCSimIO/RootFile $OUT/chunk${K}_s$s.root
/run/beamOn $nev
EOF
    } > $m
    run_wcsim $m "$OUT/chunk${K}_s$s.log"
    ROOTF=$OUT/chunk${K}_s$s.root
    # ANNIE's WCSim names its file <RootFile>_<run>.root (one run here: _0), the LAPPDs in <RootFile>_lappd_0.root
    if [ "$DET" = annie ]; then ROOTF=$OUT/chunk${K}_s$s.root_0.root; fi
    singularity exec $B $IMG bash -c "$ENV; export LD_LIBRARY_PATH=$LIB:\$LD_LIBRARY_PATH; \
      root -l -b -q -e 'gSystem->Load(\"libWCSimRoot\"); gInterpreter->AddIncludePath(\"$INC\")' '$HERE/dump_hits.C(\"$ROOTF\", \"$OUT/chunk${K}_s$s\")'" \
      > "$OUT/chunk${K}_s${s}_dump.log" 2>&1 < /dev/null || { tail -20 "$OUT/chunk${K}_s${s}_dump.log"; exit 1; }
    grep dump_hits "$OUT/chunk${K}_s${s}_dump.log"
    echo "source $s: $nev events x $BATCH photons"
  fi
  s=$((s + 1))
done
singularity exec $B $DEV python3 "$HERE/to_hits.py" "$OUT" "$K" "$BATCH" "$CFG"
rm -rf "$tmp"
