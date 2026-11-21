#!/bin/bash
# Build WCSim inside an image (run it as a batch job):
#
#   build.sh IMAGE SETUP SRC BUILD [cmake|make]
#
# SETUP: a script sourced first in the image (its Geant4 and ROOT environment): env_hk.sh for hk-software_main.sif
# (Geant4 10.3.3), "" for a Geant4 10.7.4 + ROOT 6.26 image (its thisroot.sh and geant4.sh are sourced).
# The builds the reference products came from (refs/make_store.sh), each a checkout of its commit with patches/ applied:
#   build_hk       WCSim/WCSim e2dc7a48 (unpatched) in hk-software_main.sif: the SK and WCTE hits
#   build_hk_hits  e2dc7a48 + wcsim_hk_hits.patch (HyperK's obsolete-geometry exit commented out) in hk-software_main.sif:
#                  the Hyper-K and IWCD hits
#   build_main     e2dc7a48 + wcsim_main_gdml.patch (a G4GDMLParser for /persistency/gdml/write) in a Geant4 10.7.4 image:
#                  the SK and WCTE GDML exports
#   build_hk_export  e2dc7a48 + wcsim_hk_export.patch in a Geant4 10.7.4 image: the Hyper-K and IWCD GDML exports
#   build_annie_ref  ANNIEsoft/WCSim e88314b + wcsim_annie_gdml.patch in anniesoft_wcsim_latest.sif (its Geant4 10.1.3
#                  has GDML): ANNIE's hits and GDML export
# BIND: the singularity bind paths of your site.
set -euo pipefail
IMG=$1; SETUP=$2; SRC=$3; B=$4; SYS=${5:-cmake}
mkdir -p "$B"
singularity exec ${BIND:+-B $BIND} "$IMG" bash -c "
set -e
if [ -n '$SETUP' ]; then source '$SETUP'; else source /app/root/bin/thisroot.sh; source \$(geant4-config --prefix)/bin/geant4.sh; fi
geant4-config --version; root-config --version
cd '$B'
if [ $SYS = cmake ]; then
  cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX='$B/install' -DWCSim_Geant4_UIVis=OFF '$SRC'
  make -j16
  make install
else
  cmake '$SRC'
  make -j16
fi
"
