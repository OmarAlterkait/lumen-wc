"""lumen-wc's recipes, value sets and references: each value set loads with its provenance and reproduces WCSim's own
numbers; each timed group has its readout gate; the reference engine gates. (Moved from lumen's unit tests.)"""

import json
from importlib import resources
from pathlib import Path

import jax.numpy as jnp
import numpy as np
import pytest

from lumen import sensors, testing
from lumen.readout import hits as hm
from lumen_wc import DETECTORS, REFERENCES, wcsim

SETS = ("sk_r3600", "wcte_r14374", "wcsim_annie_R7081", "wcsim_annie_D784KFLB", "wcsim_annie_R5912HQE",
        "wcsim_annie_R7081HQE", "wcsim_bl20_hqe", "wcsim_r14374", "wcsim_r14374_fdod", "wcsim_r12199_02")  # fmt: skip


def _load(name):
    return testing.load_value_set(f"lumen_wc:{name}")


def _numbered(d):
    """The value set's fields a source or a choice must account for: every non-null top-level field, and each
    numeric field of the front end."""
    skip = {"schema", "model", "name", "readout", "provenance", "frontend"}
    out = {k for k, v in d.items() if k not in skip and v is not None}
    return out | {f"frontend/{k}" for k, v in d["frontend"].items() if not isinstance(v, str)}


@pytest.mark.parametrize("name", SETS)
def test_every_number_has_a_source_or_is_a_stated_choice(name):
    """Each field is either transcribed (provenance.fields: file:line) or a stated choice of this package
    (provenance.choices: the value and its reason), never both and never neither."""
    d = json.loads((Path(str(resources.files("lumen_wc"))) / "sensor_values" / f"{name}.json").read_text())
    fields, choices = d["provenance"]["fields"], d["provenance"]["choices"]
    assert not set(fields) & set(choices)
    assert _numbered(d) <= set(fields) | set(choices), _numbered(d) - set(fields) - set(choices)


@pytest.mark.parametrize("name", SETS)
def test_shipped_set_loads_with_provenance(name):
    testing.check_value_set(f"lumen_wc:{name}")


def test_unverified_timing_warns():
    with pytest.warns(UserWarning, match="timing unverified"):
        sensors.model_from_dict(
            json.loads((Path(str(resources.files("lumen_wc"))) / "sensor_values/sk_r3600.json").read_text())
        )


def test_sk_spe_and_threshold_reproduce_wcsim():
    """The SK set's SPE table is WCSim's rn1pe (mean 0.9993 pe) and its threshold gives WCSim's A_1 = 0.7390."""
    m = _load("sk_r3600")
    mean, _ = m.charge.moments({"pdf": jnp.asarray(m.values["charge/pdf"])})
    np.testing.assert_allclose(float(mean), 0.99935, atol=2e-5)  # the SPE mean of WCSim's SK charge table
    v = m.split(m.defaults("pmt", 1), "pmt")
    v = {
        k: ({a: jnp.asarray(b, jnp.float32) for a, b in x.items()} if isinstance(x, dict) else x) for k, x in v.items()
    }
    n, n_neg, q = hm.charge_grid(m)
    dq = m.charge_step
    spe = np.asarray(m.charge.pmf(v["charge"], np.r_[q - dq / 2, q[-1] + dq / 2]))
    acc = np.asarray(m.threshold.accept(v["threshold"], jnp.asarray(q, jnp.float32)))
    np.testing.assert_allclose(np.sum(spe * acc), 0.73902, atol=1e-3)  # the reference's closed form


def test_sk_ce_is_current_wcsim_s_flat_100_percent():
    """SK's collection efficiency is WCSim's current one, 100 % at every angle (the 2011 table is not used)."""
    m = _load("sk_r3600")
    assert np.all(np.asarray(m.values["ce"]) == 1.0) and "GetCollectionEfficiencyArray" in m.provenance["fields"]["ce"]


@pytest.mark.parametrize("name", SETS)
def test_wcsim_sets_hold_the_datasheet_qe(name):
    """The WCSim sets' QE is the datasheet QE as WCSim publishes it (the cathode model divides by its own absorptance,
    lumen.surfaces.types.per_normal), said in the provenance; no fixed factor is divided into it."""
    text = _load(name).provenance["fields"]["qe"]
    assert "the datasheet QE as published" in text and "0.68" not in text and "version" not in text


HK_GATES = {"hk": 1400.0, "hk_id": 1450.0, "hk_od": 1450.0, "iwcd": 1050.0}  # ns: the shipped GDMLs' rule values


@pytest.mark.parametrize("name", sorted(HK_GATES))
def test_the_readout_gate_is_the_rule_on_the_detector_volume(name):
    """Each WCSim recipe's gate is computed at conversion from its GDML (wcsim.readout_gate: 950 ns after the trigger
    plus the detector volume's longest chord at the water's group speed, rounded up to 50 ns), on every timed group;
    the shipped GDMLs give HK 1400 ns (94 m), the realistic HK FD 1450 ns (98 m) and IWCD 1050 ns (12 m)."""
    from lumen import DetectorEntry
    from lumen_wc import inputs

    entry = DETECTORS[name]
    with inputs.gdml_file(entry.gdml) as gdml:
        made = entry.recipe(gdml, {})
    assert {name} == testing.check_readout_gates({name: DetectorEntry(recipe=made, gdml=entry.gdml)})
    assert {g.readout["gate"] for g in made.groups} == {(0.0, HK_GATES[name])}


def test_the_readout_gate_rule(tmp_path):
    """A tube of SK's WCSim water volume (35.8 m x 36.2 m: a 51 m chord, 235 ns) gives 1200 ns."""
    (tmp_path / "t.gdml").write_text(
        '<gdml><solids><tube name="b" rmax="17919.5388031059" z="36242" deltaphi="360" aunit="deg" lunit="mm"/>'
        '</solids><structure><volume name="WCBarrel0x1"><solidref ref="b"/></volume></structure></gdml>'
    )
    assert wcsim.detector_chord(tmp_path / "t.gdml") == pytest.approx(50.97, abs=0.01)
    assert wcsim.readout_gate(tmp_path / "t.gdml") == (0.0, 1200.0)


def test_every_input_is_checked_by_one_rule(tmp_path):
    """Every file a conversion reads has a sha256 this package records; another file, or one with another sha256, is
    refused before anything reads it."""
    import lumen_wc
    from lumen_wc import inputs

    d = tmp_path / "gdml-repaired"
    d.mkdir()
    (d / "sk.gdml").write_text("<gdml/>")
    with pytest.raises(inputs.InputError, match="not the expected"), lumen_wc.prepare(wcsim.SK, d / "sk.gdml", {}):
        pass
    with pytest.raises(inputs.InputError, match="records no sha256"):
        lumen_wc.expected(tmp_path / "other.gdml")


def test_the_engine_lumen_follows_gates_and_other_references_of_its_detector_cross_check():
    """g4ref (Geant4 10.7.4; what g4ref changes in it: refs/README.md) on the overlap-free export gates, its run on
    the original GDML named beside it; a detector's other simulation is reported where such a g4ref one exists (the
    WCSim runs of WCTE, ANNIE, SK and Hyper-K), and gates where none does (IWCD's). No entry scales a parameter to
    pass."""
    from lumen.compare import references

    gate = testing.check_references_gate(REFERENCES)
    g4 = ("annie_g4", "wcte_g4", "sk_g4", "hk_g4")
    assert all(gate[n] for n in g4) and gate["iwcd"]
    m = (REFERENCES,)
    for n in g4:
        assert references.original(references.spec("charge", n, m)["reference"], m) == f"{n[:-3]}-g4ref-original"
    assert not any(gate[n] for n in ("wcte", "annie", "sk", "hk"))  # ANNIE's WCSim: its QE from the value sets


def test_every_detector_s_mc_gate_inputs_are_in_the_manifest():
    """Each detector's MC gate photon file and reference record are files of a manifest product (sha256 pinned)."""
    import json

    m = json.loads(Path(REFERENCES).read_text())
    mc = {e["name"]: e for e in m["checks"]["mc"]}
    assert set(mc) == set(DETECTORS) - {"hk", "hk_id", "hk_od", "iwcd"}
    for e in mc.values():
        files = m["products"][e["reference"]]["files"]
        assert e["photons"] in files and e["record"] in files


HK_REFERENCE = {"hk": "wcsim-hk-e2dc7a48", "hk_id": "wcsim-hk-id-e2dc7a48", "hk_od": "wcsim-hk-od-e2dc7a48",
                "iwcd": "wcsim-iwcd-e2dc7a48"}  # fmt: skip


@pytest.mark.parametrize("name", sorted(HK_REFERENCE))
def test_shipped_gdml_is_the_one_its_wcsim_reference_ran(name):
    """Hyper-K's and IWCD's GDML ship here (xz): decompressed, each has the sha256 and size gdml/SOURCES.json records;
    it is the repaired copy (lumen.gdml.repair) of the export whose sha256 is that of the GDML in its WCSim charge
    reference (the manifest), so lumen converts what WCSim ran."""
    import hashlib
    import lzma

    from lumen_wc import inputs

    gdml = DETECTORS[name].gdml
    src = inputs.shipped()[gdml.name[: -len(".xz")]]
    data = lzma.open(gdml).read()
    assert len(data) == src["bytes"] and hashlib.sha256(data).hexdigest() == src["sha256"]
    assert src["commit"] == "e2dc7a48b1f83c74a541123542606a90d7b67a6f" and src["url"].endswith(src["commit"])
    product = json.loads(Path(REFERENCES).read_text())["products"][HK_REFERENCE[name]]
    assert product["files"][f"{name}.gdml"] == "sha256:" + src["export_sha256"]
    assert "GROUPVEL" in src["repair"] and src["bytes"] - src["export_bytes"] == 3  # 3 inf -> 1e30
    with inputs.gdml_file(gdml) as path:
        assert path.name == f"{name}.gdml" and inputs.sha256(path) == src["sha256"]


def test_a_changed_shipped_gdml_is_refused(tmp_path):
    import lzma

    from lumen_wc import inputs

    bad = tmp_path / "iwcd.gdml.xz"
    bad.write_bytes(lzma.compress(b"<gdml/>"))
    with pytest.raises(inputs.InputError, match="sha256"), inputs.gdml_file(bad):
        pass


@pytest.mark.slow  # Hyper-K: the largest conversion (IWCD, below, runs by default)
def test_hk_converts_from_its_shipped_gdml(tmp_path):
    """Hyper-K converts without a data directory and loads with the tubes of its WCSim reference."""
    import lumen

    det = lumen.load(lumen.convert("lumen_wc:hk", out=tmp_path / "hk.lumen", data=tmp_path / "unused"))
    want = json.loads(Path(REFERENCES).read_text())["products"]["wcsim-hk-e2dc7a48"]["sensors"]
    assert len(det.sensor_table().name) == want


def test_iwcd_converts_from_its_shipped_gdml(tmp_path):
    """IWCD (the smallest shipped GDML) converts without a data directory and loads with its WCSim tubes."""
    import lumen

    det = lumen.load(lumen.convert("lumen_wc:iwcd", out=tmp_path / "iwcd.lumen", data=tmp_path / "unused"))
    want = json.loads(Path(REFERENCES).read_text())["products"]["wcsim-iwcd-e2dc7a48"]["sensors"]
    assert len(det.sensor_table().name) == want
