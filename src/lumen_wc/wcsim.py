"""Recipes for the WCSim detectors (SK, WCTE, ANNIE, Hyper-K, IWCD), from the GDML WCSim itself exports.

WCSim semantics these recipes follow (WCSim e2dc7a48 source):

- The hit. WCSim's sensitive detector is the PMT glass; WCSimWCSD::ProcessHits counts a photon killed in the glass on
  a step whose post volume is InteriorWCPMT, i.e. absorbed at the glass to interior border surface
  (GlassCathodeSurface), whether Geant4 calls it Detection or Absorption. So the sensors are the InteriorWCPMT
  volumes, counted across their GDML border surfaces (rule ``border_into``) with every absorption entering detected
  (``efficiency`` 1). The reverse border (AirCathodeSurface, where the GDML has one: WCTE) counts with its
  EFFICIENCY, credited to the interior it leaves (WCSimOpBoundaryProcess::DoAbsorption and ProcessHits_boundary).
- Quantum and collection efficiency are off in the reference runs; they are applied after tracking, by the sensor
  model ``lumen:sensor`` with a value set transcribed from WCSim per sensor group (SK ``lumen_wc:sk_r3600``, WCTE
  ``lumen_wc:wcte_r14374``,
  ANNIE one group per tank tube type, ``lumen_wc:wcsim_annie_<type>``). The model applies
  the efficiency after tracking, so every absorption entering is counted, as WCSim's sensitive detector does.
- Only WCSim's photocathode model 0 (= G4OpBoundaryProcess) is implemented; models 1 and 2 (thin-film cathodes) are
  refused, as they would not show in the GDML.
- Hyper-K and IWCD (WCSim e2dc7a48 ``HyperK`` at 20 % coverage, ``HyperK_HybridmPMT_IDonly_Realistic``,
  ``HyperK_HybridmPMT_WithOD_Realistic``, ``IWCD_mPMT``). Their GDML comes from WCSim with three export-time changes
  that leave the geometry as WCSim builds it: the mPMTs' parameterised PMTs (G4PVParameterised, which lumen does not
  read) written as plain placements at the parameterisation's own transformations; the realistic placement's
  assemblies deregistered before writing, so their imprints are written as the plain placements they are (Geant4
  10.7's GDML writer crashed on the assemblies' deleted dummy PMTs); and the obsolete-geometry exit of ``HyperK``
  commented out, as its message instructs. A hybrid has one WCSim collection per tube type (``glassFaceWCPMT``,
  ``glassFaceWCPMT2``, ``glassFaceWCPMT_OD``), each with its own InteriorWCPMT logical volume. Each sensor's
  collection is the id map's column ``collection`` (``glass_faces``), by which the charge check groups the
  sensors and each collection is its own sensor group with its tube's value set: ``bl``
  (``lumen_wc:wcsim_bl20_hqe``, BoxandLine20inchHQE), ``mpmt`` (``lumen_wc:wcsim_r14374``, the HK mPMT's
  PMT3inchR14374), ``od`` (``lumen_wc:wcsim_r14374_fdod``, the OD's PMT3inchR14374_FDOD). IWCD:
  ``lumen_wc:wcsim_r12199_02`` (PMT3inchR12199_02).
- ANNIE's StainlessSteel mesh (ABSLENGTH 1e-11 m) is bound opaque by the general absorbed-at-entry rule
  (``lumen.build.import_rules``).

The GDML exports have defects Geant4 refuses: SK, WCTE, Hyper-K and IWCD write inf in one GROUPVEL table (3 values, on
surfaces, which no Geant4 process reads), ANNIE 40 denormal RINDEX values (in one table). Their sources (``DETECTORS``)
are the copies ``python -m lumen.gdml.repair`` writes (inf -> 1e30, denormal -> 0, nothing else changed), the ones their
g4ref references loaded too; Hyper-K's and IWCD's ship in this package (``gdml/``, xz, with ``gdml/SOURCES.json``).
"""

from __future__ import annotations

import dataclasses
import re

from lumen import Recipe, SensorGroup
from lumen.format import schema

DETECTOR = "WCBarrel"  # WCSim's water volume (WC is air, expHall vacuum)
SENSOR_LV = "InteriorWCPMT"
ANNIE_TANK_TYPES = ("R7081", "D784KFLB", "R5912HQE", "R7081HQE")  # SetANNIEPhase2Geometryv7's tank collections
# The readout gate, one rule for every WCSim detector (``readout_gate``): WCSim's NDigits trigger keeps the hits up to
# 950 ns after the trigger (WCSimWCTrigger.hh:113, e2dc7a48), and the trigger comes with the first light. A gate from
# the emission covers that and the light's crossing of the detector volume: its longest chord (``detector_chord``) at
# the group speed in water, rounded up to GATE_STEP.
WCSIM_POST_TRIGGER = 950.0  # ns
# ns/m: 1 / the group speed in water at 400 nm, WCSim's water GROUPVEL there (SK's and WCTE's GDML: 0.2171 m/ns, 4.606
# ns/m; not read at conversion, which would need lumen's GDML reader here; the gate rounds the crossing up to GATE_STEP)
WATER_NS_PER_M = 4.6
GATE_STEP = 50.0  # ns


def detector_chord(gdml, volume: str = DETECTOR) -> float:
    """Return the longest chord (m) of the detector volume's solid in a GDML file: a full tube's (hypot of its
    diameter and length) or a full regular polyhedra's (its z planes' outer tangent radius over cos(pi / sides))."""  # noqa: D205, D209
    import lzma
    import math
    import xml.etree.ElementTree as ET

    units = {"mm": 1e-3, "cm": 1e-2, "m": 1.0}
    opener = lzma.open if str(gdml).endswith(".xz") else open
    solids: dict = {}
    ref = None
    with opener(gdml, "rb") as f:
        for _, el in ET.iterparse(f):
            tag = el.tag.rsplit("}", 1)[-1]
            if tag in ("tube", "polyhedra"):
                solids[el.get("name")] = el
                continue
            if tag == "volume" and re.fullmatch(rf"{volume}(0x[0-9a-f]+)?", el.get("name", "")):
                ref = el.find("solidref").get("ref")
            if tag not in ("zplane", "solidref"):  # read at their parent's end
                el.clear()
    if ref not in solids:
        raise ValueError(f"{gdml}: the detector volume {volume!r} is not a tube or polyhedra (its solid {ref!r})")
    s = solids[ref]
    u = units[s.get("lunit", "mm")]
    if float(s.get("deltaphi", 360)) != 360 or s.get("aunit", "deg") != "deg":
        raise ValueError(f"{gdml}: the detector volume's solid {ref!r} is not a full turn")
    if s.tag.rsplit("}", 1)[-1] == "tube":
        return math.hypot(2 * float(s.get("rmax")) * u, float(s.get("z")) * u)
    zs = [(float(z.get("z")) * u, float(z.get("rmax")) * u) for z in s if z.tag.rsplit("}", 1)[-1] == "zplane"]
    r = max(rm for _, rm in zs) / math.cos(math.pi / int(s.get("numsides")))
    return math.hypot(2 * r, max(z for z, _ in zs) - min(z for z, _ in zs))


def readout_gate(gdml, volume: str = DETECTOR) -> tuple[float, float]:
    """Return a WCSim detector's readout gate, ns after emission: WCSIM_POST_TRIGGER after the light crosses the
    detector volume (its longest chord at WATER_NS_PER_M), the crossing rounded up to GATE_STEP."""  # noqa: D205, D209
    import math

    crossing = detector_chord(gdml, volume) * WATER_NS_PER_M
    return 0.0, WCSIM_POST_TRIGGER + GATE_STEP * math.ceil(crossing / GATE_STEP)


def pmt_group(name: str, values: str, collection: str | None = None) -> SensorGroup:
    """Return a ``border_into`` group of WCSim tubes read by ``lumen:sensor`` with value set ``values``; its readout
    gate is set at conversion (``Gated``). ``collection``: only the tubes of that WCSim collection (the id map's column
    ``collection``); None: every tube."""  # noqa: D205, D209
    return SensorGroup(name, rule="border_into", lv_pattern=f"^{SENSOR_LV}", values=values,
                       where=None if collection is None else {"collection": collection})  # fmt: skip


@dataclasses.dataclass(frozen=True)
class Gated:
    """A WCSim detector's recipe as its package entry holds it: called with its GDML at conversion (the package's
    ``prepare``), it returns ``recipe`` with every group's readout gate ``readout_gate(gdml)``."""  # noqa: D205, D209

    recipe: Recipe

    @property
    def name(self) -> str:
        """The recipe's name."""
        return self.recipe.name

    @property
    def detector_volume(self) -> str:
        """The recipe's detector volume."""
        return self.recipe.detector_volume

    def __call__(self, gdml, inputs=None) -> Recipe:
        """Return the recipe with its groups' readout gate computed from the GDML's detector volume."""
        gate = readout_gate(gdml, self.recipe.detector_volume)
        groups = tuple(dataclasses.replace(g, readout={**(g.readout or {}), "gate": gate}) for g in self.recipe.groups)
        return dataclasses.replace(self.recipe, groups=groups)


def recipe(name: str, values, detector_volume: str = DETECTOR, decisions=(), inputs=(), **kw) -> Gated:
    """Return a WCSim detector's recipe (``Gated``: its readout gate set from its GDML at conversion); ``values`` is
    its PMTs' value set (``lumen:sensor``) read in one group (``pmt_group``), or its sensor groups. Every recipe
    records G4OpWLS's profile as WCSim runs it (``wls_exponential``)."""  # noqa: D205, D209
    groups = (pmt_group("pmt", values),) if isinstance(values, str) else tuple(values)
    return Gated(Recipe(name=name, detector_volume=detector_volume, groups=groups,
                        decisions=(wls_exponential, *decisions), inputs=tuple(inputs), **kw))  # fmt: skip


def collection_columns(df, paths, inputs) -> dict:
    """Return the id map's per-sensor WCSim collection (``glass_faces``)."""
    return {"collection": glass_faces(df, paths)}


def glass_faces(df: schema.DetectorFile, paths) -> list:
    """Return each sensor's WCSim collection: the name of the glass face placed beside its interior in its tube.

    WCSim names a tube type's glass face ``glassFaceWCPMT<suffix>``: ``glassFaceWCPMT`` (the ID's first collection),
    ``glassFaceWCPMT2`` (a hybrid's second), ``glassFaceWCPMT_OD`` (the OD), ``glassFaceWCPMT_<type>`` (ANNIE's tank
    types).
    """
    holder: dict[str, set] = {}
    for name, v in df.volumes.items():
        for i in v.daughters:
            holder.setdefault(df.placements[i].volume, set()).add(name)
    out = []
    for p in paths:
        lv = str(p).rsplit("/", 1)[-1].split("#")[0]
        cols = {
            m.group(1)
            for n in holder.get(lv, set())
            for i in df.volumes[n].daughters
            for m in [re.match(r".*?(glassFaceWCPMT\w*?)(?:0x[0-9a-f]+)?$", df.placements[i].volume)]
            if m
        }
        if len(cols) != 1:
            raise ValueError(f"glass_faces: {p!r}: interior LV {lv!r} has glass faces of {sorted(cols)}")
        out.append(cols.pop())
    return out


def wls_exponential(df: schema.DetectorFile, inputs: dict) -> schema.DetectorFile:
    """Record G4OpWLS's exponential time profile on every material with a WLSTIMECONSTANT (HK's OD plates; no other
    WCSim detector here has one, so for them this changes nothing).

    WCSim runs G4OpWLS with the exponential profile: WCSimOpticalPhysics.cc constructs it with "delta", but
    WCSimPhysicsListFactory::InitializeList sets "exponential" (WCSimPhysicsListFactory.cc:154, e2dc7a48) before the
    processes are built; a detector file records none as Geant4's default, delta (``lumen.rules.optics``).
    """
    o = schema.OpticsModel(
        "geant4",
        settings={"wls_time_profile": "exponential"},
        origin="recipe",
        note="G4OpWLS's exponential time profile, as WCSim runs it (WCSimPhysicsListFactory.cc:154, e2dc7a48)",
    )
    mats = {n: dataclasses.replace(m, optics=o) if "WLSTIMECONSTANT" in m.properties else m
            for n, m in df.materials.items()}  # fmt: skip
    return dataclasses.replace(df, materials=mats)


SK = recipe("sk", "lumen_wc:sk_r3600")
WCTE = recipe("wcte", "lumen_wc:wcte_r14374")
HK = recipe("hk", "lumen_wc:wcsim_bl20_hqe")  # HK's generic cylinder
IWCD = recipe("iwcd", "lumen_wc:wcsim_r12199_02")
# the realistic HK FD: one group per WCSim collection (the id map's column "collection"), each with its tube's values
HK_BL = pmt_group("bl", "lumen_wc:wcsim_bl20_hqe", "glassFaceWCPMT")
HK_MPMT = pmt_group("mpmt", "lumen_wc:wcsim_r14374", "glassFaceWCPMT2")
HK_ODPMT = pmt_group("od", "lumen_wc:wcsim_r14374_fdod", "glassFaceWCPMT_OD")
# the inner detector: its 20-inch Box&Line tubes and its mPMTs' 3-inch tubes
HK_ID = recipe("hk_id", (HK_BL, HK_MPMT), sensor_columns=collection_columns)
# the full HK FD: the inner detector and the OD's 3-inch tubes with their WLS plates
HK_OD = recipe("hk_od", (HK_BL, HK_MPMT, HK_ODPMT), sensor_columns=collection_columns)
# ANNIE: one group per tank tube type, each with its type's value set (WCSim's Multi_Tank_Types)
ANNIE_FACE = "glassFaceWCPMT_"
ANNIE = recipe(
    "annie",
    tuple(pmt_group(t, f"lumen_wc:wcsim_annie_{t}", ANNIE_FACE + t) for t in ANNIE_TANK_TYPES),
    sensor_columns=collection_columns,
)
