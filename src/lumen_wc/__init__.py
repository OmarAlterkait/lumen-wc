"""lumen for water Cherenkov detectors (WCSim: Super-K, WCTE, ANNIE, Hyper-K, IWCD).

    import lumen
    from lumen.compare import references
    path = lumen.convert("lumen_wc:sk", out="sk.lumen", data=references.store())   # the recipe and its GDML, once
    det = lumen.load(path)

The recipes are ``lumen_wc.wcsim``; the PMT value sets are ``lumen_wc:<set>`` (``sensor_values/<set>.json``); the
reference manifest of the comparisons is ``REFERENCES`` (``python -m lumen.compare ... --package lumen_wc``).
"""

from __future__ import annotations

from pathlib import Path

from lumen import DetectorEntry
from lumen.inputs import package
from lumen_wc import wcsim
from lumen_wc.inputs import GDML_DIR

REFERENCES = Path(__file__).parent / "references.json"
# name: lumen.DetectorEntry (the recipe, made from its GDML at conversion: wcsim.Gated; its GDML under the data
# directory, the recipe's inputs there). SK, WCTE and
# ANNIE are the repaired copies Geant4 loads (python -m lumen.gdml.repair), fetched with the product gdml-repaired when
# the directory lacks them. Hyper-K and IWCD: their GDMLs ship here (xz, gdml/SOURCES.json), ``data`` is not read for
# them
DETECTORS: dict[str, DetectorEntry] = {
    "sk": DetectorEntry(recipe=wcsim.SK, gdml="gdml-repaired/sk.gdml"),
    "wcte": DetectorEntry(recipe=wcsim.WCTE, gdml="gdml-repaired/wcte.gdml"),
    "annie": DetectorEntry(recipe=wcsim.ANNIE, gdml="gdml-repaired/annie_v2.gdml"),
    "hk": DetectorEntry(recipe=wcsim.HK, gdml=GDML_DIR / "hk.gdml.xz"),
    "hk_id": DetectorEntry(recipe=wcsim.HK_ID, gdml=GDML_DIR / "hk_id.gdml.xz"),
    "hk_od": DetectorEntry(recipe=wcsim.HK_OD, gdml=GDML_DIR / "hk_od.gdml.xz"),
    "iwcd": DetectorEntry(recipe=wcsim.IWCD, gdml=GDML_DIR / "iwcd.gdml.xz"),
}


# the package's prepare (lumen.convert("lumen_wc:NAME")) and the sha256 of each file a conversion reads: lumen's one
# input pipeline (lumen.inputs.package); a recipe made from its GDML (wcsim.Gated: its readout gate from the detector
# volume) is made from the GDML as converted
prepare, expected = package(REFERENCES, GDML_DIR)
