#!/bin/bash
# Build the reference store: every product lumen-wc's checks read, reduced by tools/g4ref/reduce.py, read-only.
#
#   make_store.sh STORE G4REF_RUNS        (run it as a batch job: it hashes the WCSim images, 3.6 GB)
#
# The WCSim products are the runs of refs/wcsim/run.sh (hits mode; builds in refs/wcsim/build.sh): SK and WCTE in
# hk-software's image, ANNIE in anniesoft's, Hyper-K and IWCD in hk-software's with wcsim_hk_hits.patch, into
# $LUMEN_SITE_DATA/lumen/wcsim/out/<det>_main; their sources are refs/wcsim/cfg; each keeps the GDML WCSim ran (Hyper-K's
# and IWCD's exported by refs/wcsim/run.sh gdml with the wcsim_hk_export.patch build, in WCSIM_GDML). gdml-repaired: the
# repaired copies of the SK, WCTE and ANNIE exports (python -m lumen.gdml.repair). The g4ref products are the runs of the reference manifest's g4ref
# products (src/lumen_wc/references.json: their producers' run blocks; lumen's tools/g4ref/references.sh --runs) in
# G4REF_RUNS. Prints each product's manifest entry.
set -euo pipefail
STORE=$1; RUNS=$2
HERE=${G4REF_TOOLS:?the tools/g4ref directory of lumen (reduce.py, make_store.sh)}
D=${LUMEN_SITE_DATA:?the directory holding lumen/wcsim and lumen/g4ref}
export IMAGE=${IMAGE:?the container image the g4ref runs used} G4REF_SRC=${G4REF_SRC:?the g4ref source file the runs were built from}
W=$D/lumen/wcsim
G=${WCSIM_GDML:?the directory of the Hyper-K and IWCD GDML exports (hk, hkid, hkod, iwcd .gdml)}
LUMEN_PY=${LUMEN_PY:?a python with lumen importable (python -m lumen.gdml.repair)}
CFG=$(cd "$(dirname "$0")" && pwd)/wcsim/cfg
TMP=$(mktemp -d -p "${STORE_TMP:-/tmp}")
trap 'rm -rf "$TMP"' EXIT
R="python3 $HERE/reduce.py"
have() { [ -e "$STORE/$1" ] && echo "$1: in the store already (a product is never overwritten)"; }
sha() { sha256sum "$1" | cut -d' ' -f1; }

wcsim() {   # wcsim FILE DET COMMIT REPOSITORY IMAGE GEANT4 RESPONSE
  cat > "$1" << EOF
{"tool": "WCSim", "repository": "$4", "commit": "$3", "image": "$(basename "$5")", "image_sha256": "$(sha "$5")", "geant4": "$6",
 "macro": "WCSim macro refs/wcsim/macros/$2.mac", "tuning": "$(sed -n 's/^# tuning: //p' "$(dirname "$0")/wcsim/macros/$2.mac")",
 "harness": "refs/wcsim/run.sh hits: WCSim's true-hits output, every PMT collection with its own tube ids (dump_hits.C, to_hits.py)",
 "response": "$7", "hit": "a photon absorbed at WCSim's photocathode boundary (glass to InteriorWCPMT), true hits of trigger 0"}
EOF
}
wcsim "$TMP/sk.json" sk e2dc7a48b1f83c74a541123542606a90d7b67a6f WCSim/WCSim $W/images/hk-software_main.sif 10.3.3 \
  "DoNotApplyQE, collection efficiency off, no dark noise"
wcsim "$TMP/wcte.json" wcte e2dc7a48b1f83c74a541123542606a90d7b67a6f WCSim/WCSim $W/images/hk-software_main.sif 10.3.3 \
  "DoNotApplyQE, collection efficiency off, no dark noise"
wcsim "$TMP/annie.json" annie e88314b31266255ed02a95ce87677f92d4c2db22 ANNIEsoft/WCSim $W/images/anniesoft_wcsim_latest.sif \
  10.1.3 "QE kept (Multi_Tank_Types: no DoNotApplyQE in ANNIE's WCSim), collection efficiency off"

have wcsim-sk-e2dc7a48 || $R hits $W/out/sk_main "$STORE" wcsim-sk-e2dc7a48 --config $CFG/sk.cfg --producer "$TMP/sk.json" \
  --input sk.gdml=$W/out/sk.gdml
have wcsim-wcte-e2dc7a48 || $R hits $W/out/wcte_main "$STORE" wcsim-wcte-e2dc7a48 --config $CFG/wcte.cfg --producer "$TMP/wcte.json" \
  --input wcte.gdml=$W/out/wcte.gdml
have wcsim-annie-e88314b || $R hits $W/out/annie_main "$STORE" wcsim-annie-e88314b --config $CFG/annie.cfg --producer "$TMP/annie.json" \
  --input annie_v2.gdml=$W/out/annie_v2.gdml --input tuning_parameters.mac=$W/src_annie_ref/macros/tuning_parameters.mac

# Hyper-K and IWCD (WCSim e2dc7a48 + wcsim_hk_hits.patch; dark noise 0 in every element run.sh's DARK_ELEMENTS names)
HK="DoNotApplyQE, collection efficiency off, no dark noise"
HKI=$W/images/hk-software_main.sif
wcsim "$TMP/hk.json" hk e2dc7a48b1f83c74a541123542606a90d7b67a6f WCSim/WCSim $HKI 10.3.3 \
  "$HK; HyperK's obsolete-geometry exit commented out (the only change to WCSim)"
wcsim "$TMP/hkid.json" hkid e2dc7a48b1f83c74a541123542606a90d7b67a6f WCSim/WCSim $HKI 10.3.3 "$HK; dark noise 0 in tank and tankPMT2"
wcsim "$TMP/hkod.json" hkod e2dc7a48b1f83c74a541123542606a90d7b67a6f WCSim/WCSim $HKI 10.3.3 \
  "$HK; dark noise 0 in tank, tankPMT2 and OD; tuning_parameters_hkfd.mac; G4OpWLS time profile exponential (WCSim's own: WCSimPhysicsListFactory.cc:154)"
wcsim "$TMP/iwcd.json" iwcd e2dc7a48b1f83c74a541123542606a90d7b67a6f WCSim/WCSim $HKI 10.3.3 "$HK"
have wcsim-hk-e2dc7a48 || $R hits $W/out/hk_main "$STORE" wcsim-hk-e2dc7a48 --config $CFG/hk.cfg --producer "$TMP/hk.json" \
  --input hk.gdml=$G/hk.gdml
have wcsim-hk-id-e2dc7a48 || $R hits $W/out/hkid_main "$STORE" wcsim-hk-id-e2dc7a48 --config $CFG/hkid.cfg \
  --producer "$TMP/hkid.json" --input hk_id.gdml=$G/hkid.gdml
have wcsim-hk-od-e2dc7a48 || $R hits $W/out/hkod_main "$STORE" wcsim-hk-od-e2dc7a48 --config $CFG/hkod.cfg \
  --producer "$TMP/hkod.json" --input hk_od.gdml=$G/hkod.gdml
have wcsim-iwcd-e2dc7a48 || $R hits $W/out/iwcd_main "$STORE" wcsim-iwcd-e2dc7a48 --config $CFG/iwcd.cfg \
  --producer "$TMP/iwcd.json" --input iwcd.gdml=$G/iwcd.gdml

# the repaired copies of WCSim's SK, WCTE and ANNIE exports (the products wcsim-sk-e2dc7a48, wcsim-wcte-e2dc7a48 and
# wcsim-annie-e88314b hold the originals); the producer lists each file's edits as lumen.gdml.repair prints them
if ! have gdml-repaired; then
  for f in sk.gdml wcte.gdml annie_v2.gdml; do
    $LUMEN_PY -m lumen.gdml.repair "$W/out/$f" "$TMP/$f" > "$TMP/$f.edits"
  done
  python3 - "$TMP" > "$TMP/repaired.json" << 'EOF'
import json, sys
d = sys.argv[1]
edits = {f: "; ".join(open(f"{d}/{f}.edits").read().split("\n")).strip("; ") for f in ("sk.gdml", "wcte.gdml", "annie_v2.gdml")}
print(json.dumps({"tool": "python -m lumen.gdml.repair SRC DST: the copies of WCSim's exports Geant4 10.7.4 and 11.2.2 load; "
                  "nothing but the listed values changed", "edits": edits}, indent=1))
EOF
  $R files "$STORE" gdml-repaired sk.gdml="$TMP/sk.gdml" wcte.gdml="$TMP/wcte.gdml" annie_v2.gdml="$TMP/annie_v2.gdml" \
    --producer "$TMP/repaired.json"
fi

# the g4ref products: lumen's tools/g4ref/make_store.sh over this package's run table
bash "$HERE/make_store.sh" "$STORE" "$RUNS" --runs "$(cd "$(dirname "$0")/.." && pwd)/src/lumen_wc/references.json"
