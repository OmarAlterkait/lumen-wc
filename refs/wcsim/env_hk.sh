# the hk-software image's own Geant4 10.3.3 + ROOT (paths inside that public image, not on the host)
source /usr/local/hk/ROOT/install-Linux_x86_64-gcc_8-python_3.8.13/bin/thisroot.sh
pushd /usr/local/hk/Geant4/install-Linux_x86_64-gcc_8-python_3.8.13/bin >/dev/null; source geant4.sh; popd >/dev/null
