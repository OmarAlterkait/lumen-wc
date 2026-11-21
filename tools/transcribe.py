"""Write lumen-wc's PMT value sets (and the WCSim-emulating sets) from WCSim's sources.

    python tools/transcribe.py --wcsim WCSIM_SRC --annie ANNIE_SRC --spline SPLINE_TXT
        --out src/lumen_wc/sensor_values --tests EMULATION_DIR
    python tools/transcribe.py --wcsim WCSIM_SRC --only wcsim_bl20_hqe,wcsim_r14374 --out src/lumen_wc/sensor_values

EMULATION_DIR receives the WCSim-emulating sets, which only the readout validation against WCSim reads (kept outside
the repository).

WCSIM_SRC: WCSim develop e2dc7a4; ANNIE_SRC: WCSim annie e88314b; SPLINE_TXT: ROOT's TGraph::Eval(Q, 0, "S") of
PMT3inchR14374_WCTE's resolution graph at Q = 0.5, 0.55, ..., 4.0 (evaluated with the hk-software image's ROOT); the
transcriber checks it against the graph's knots it parses. Every number is parsed from the source (comments removed)
and every field records file:line in ``provenance.fields``; a number a set needs that no source gives is a choice of
this package, stated with its reason in ``provenance.choices``. Nothing is typed in.

Rules (lumen's docs/dev/decisions.md, 11):
- physical QE: WCSim's table without WCSim's x4/3 (SensitiveDetector_Only) nor WCTE's 1/0.73 correction factor;
  WCSim interpolates linearly over the first GetNbOfQEDefined + 1 knots, extrapolates linearly below the first knot and
  returns 0 at or above its upper cut (and at or below its lower one): knots are added where that differs from
  Geant4's constant-beyond-the-ends rule.
- physical threshold: the SKI acceptance polynomial; the dark rate is WCSim's rate times its conversion factor (the
  rate before the threshold, which is what lumen simulates).
- timing: WCSim has no per-photoelectron time spread (its smear is per digit, charge dependent). The shipped sets
  use WCSim's smear at 1 pe as a per-photoelectron Gaussian (status unverified); WCTE's pmt_tts is its PMT's
  transit-time spread and its charge-dependent resolution becomes the time walk's spread. The WCSim-emulating test
  sets use no per-photoelectron spread and WCSim's per-digit smear as the time walk.
"""

import argparse
import copy
import json
import re
from pathlib import Path

import numpy as np

from cpp_source import Source


class Wcsim:
    """A WCSim source tree: its PMT objects, the SKI digitizer, rn1pe and the QE rule, read once."""

    def __init__(self, root, tag):
        self.tag = tag
        self.pmt = Source(root, "src/WCSimPMTObject.cc", tag)
        self.hh = Source(root, "include/WCSimWCDigitizer.hh", tag)
        self.wcpmt = Source(root, "src/WCSimWCPMT.cc", tag)
        m, self.rn1pe_loop = self.wcpmt.match(r"for\s*\(\s*i\s*=\s*0;\s*i\s*<\s*(\d+);", "::rn1pe(")
        self.spe_bins = int(m.group(1))
        m, self.rn1pe_where = self.wcpmt.match(r"\(G4double\(i\s*-\s*(\d+)\)\s*\+\s*random2\)\s*/\s*([0-9.]+)",
                                               "::rn1pe(")  # fmt: skip
        self.spe_shift, self.spe_scale = int(m.group(1)), float(m.group(2))

    def spe(self, cls):
        """WCSim's single-photoelectron charge table of a tube: rn1pe's bins q = (i - shift + u) / scale."""
        cdf, where, _ = self.pmt.array(f"{cls}::Getqpe()")
        assert len(cdf) == self.spe_bins, (cls, len(cdf))
        pdf = np.clip(np.diff(np.r_[0.0, cdf]), 0.0, None)  # the 0 sentinel at the last index is never selected
        edges = (np.arange(self.spe_bins + 1) - self.spe_shift) / self.spe_scale
        table = dict(form="table", edges_pe=edges.round(10).tolist(), pdf=pdf.round(8).tolist())
        return table, f"{where} (rn1pe: {self.rn1pe_loop}, {self.rn1pe_where.split(':')[-1]})"

    def jitter(self, cls):
        """(timingConstant c, factor f, offset a, floor) of WCSim's smear max(floor, f (a + sqrt(c / Q))), and where."""
        sig = f"{cls}::HitTimeSmearing("
        c = float(self.pmt.match(r"timingConstant\s*=\s*([0-9.]+)", sig)[0].group(1))
        m, _ = self.pmt.match(r"timingResolution\s*=\s*(?:([0-9.]+)\s*\*\s*\()?\s*([0-9.]+)\s*\+\s*sqrt\(timingConstant"
                              r"/Q\)", sig)  # fmt: skip
        floor = float(self.pmt.match(r"if\s*\(timingResolution\s*<\s*([0-9.]+)\)", sig)[0].group(1))
        return c, float(m.group(1) or 1.0), float(m.group(2)), floor, self.pmt.where(sig)


def jitter_text(c, f, a, floor):
    core = f"{a} + sqrt({c} / Q)"
    return f"max({floor}, {f} ({core}))" if f != 1.0 else f"max({floor}, {core})"


def jitter_at(c, f, a, floor, q=1.0):
    return max(floor, f * (a + np.sqrt(c / q)))


WCSIM_SETS = (
    "sk_r3600",
    "wcte_r14374",
    "wcsim_annie_R7081",
    "wcsim_annie_D784KFLB",
    "wcsim_annie_R5912HQE",
    "wcsim_annie_R7081HQE",
    "wcsim_bl20_hqe",
    "wcsim_r14374",
    "wcsim_r12199_02",
    "wcsim_r14374_fdod",
)


DATASHEET_QE = (
    "; the datasheet QE as published (per photon at normal incidence): the cathode model divides by its own "
    "normal-incidence absorptance at each wavelength (lumen.surfaces.types.per_normal)"
)

SKI_DIGITIZE = "WCSimWCDigitizerSKI::DigitizeHits("
KNOT_STEP = 0.01  # nm: a cutoff written as a knot this far past an end knot
RANGES_CHOICE = (
    "the bounds of each timing value a fit may reach: lumen:sensor builds its static time grid for them (a value "
    "outside is refused); not experiment data. A time spread's width has none here: its range is lumen's derived one "
    "(lumen.rules.choices.TIME_SPREAD_REACH)"
)


def choices(spe_scale):
    """The numbers a WCSim set needs that WCSim does not give, each with its reason."""
    return {
        "efficiency": "1: no per-sensor scale (WCSim's detection is its QE and CE)",
        "t_offset_ns": "0: WCSim adds no transit offset to a hit's time",
        "gain": "1: the charge is read in photoelectrons (frontend unit pe)",
        "frontend/sampling_ns": "1: the hits' time step",
        "frontend/baseline": "0: hits have no waveform baseline",
        "frontend/noise": "0: hits have no waveform noise",
        "frontend/charge_scale": "1: WCSim's 0.985 charge factor is its tuning convention, not a physical value",
        "frontend/charge_step_pe": f"1 / (2 x {spe_scale}): two steps per bin of WCSim's charge table (rn1pe's 1 / "
        f"{spe_scale} pe)",
        "frontend/charge_max_pe": "64: the charge histogram's top",
        "ranges": RANGES_CHOICE,
        "qe/cutoff_knots": f"the knots WCSim's cutoffs add are written {KNOT_STEP} nm past the end knots (a "
        "representation of the "
        "cutoff, not a WCSim number)",
    }


def datasheet_qe(d):
    """Return value set d with its QE provenance stating the convention (the QE as the source gives it)."""
    d = copy.deepcopy(d)
    d["provenance"]["fields"]["qe"] += DATASHEET_QE
    return d


def cut_to_zero(wl, qe):
    """Return knots with an explicit 0 KNOT_STEP past an end knot whose QE is not 0: the source's cutoff written as
    data (every table is held at its end values beyond its knots, as G4PhysicsVector holds them)."""
    wl, qe = list(wl), list(qe)
    if qe[0] > 0.0:
        wl, qe = [round(wl[0] - KNOT_STEP, 4)] + wl, [0.0] + qe
    if qe[-1] > 0.0:
        wl, qe = wl + [round(wl[-1] + KNOT_STEP, 4)], qe + [0.0]
    return wl, qe


def ski(w):
    """The SKI digitizer of WCSimWCDigitizer.hh: its threshold (acceptance polynomial in x = pe + offset below limit),
    its Gaussian charge noise and its integration window, each with its line."""
    a, b, body = w.hh.function("static void Threshold(")
    sig = "static void Threshold("
    offset, ow = w.hh.match(r"x\s*=\s*pe\s*\+\s*([0-9.]+)", sig)
    limit, lw = w.hh.match(r"if\s*\(\s*x\s*<\s*([0-9.]+)\)", sig)
    noise, nw = w.hh.match(r"G4RandGauss::shoot\(0\.0,\s*([0-9.]+)\)", sig)
    window, ww = w.hh.match(r"GetDefaultIntegrationWindow\(\)\s*\{\s*return\s+([0-9.]+)\s*;")
    expr = re.search(r"std::min\(1\.0,(.*?)\);", body, re.S).group(1)
    coeffs = [float(x) for x in re.findall(r"[-+]?\d+\.?\d*", expr.replace(" ", "").replace("\n", ""))]
    assert len(coeffs) == 11, coeffs
    thr = dict(form="poly", coefficients=coeffs, offset_pe=float(offset.group(1)), limit_pe=float(limit.group(1)))
    line = lambda s: s.split(":")[-1]  # noqa: E731
    return dict(
        threshold=thr,
        threshold_where=f"{w.tag} {w.hh.rel}:{a}-{b}: the SKI acceptance (offset :{line(ow)}, limit :{line(lw)})",
        noise=float(noise.group(1)),
        noise_where=f"{nw}: Threshold's Gaussian charge noise",
        window=float(window.group(1)),
        window_where=f"{ww}: GetDefaultIntegrationWindow (no dead time)",
    )


def qe_rule(root, tag):
    """WCSim's QE rule (WCSimPMTQE.cc, flag 1): the cut energies and the knots it reads (the loop's i + 1 reaches n)."""
    q = Source(root, "src/WCSimPMTQE.cc", tag)
    m, cw = q.match(r"PhotonWavelength\s*<=\s*(\d+\.?\d*)\s*\|\|\s*PhotonWavelength\s*>=\s*(\d+\.?\d*)\)")
    _, lw = q.match(r"for\s*\(int i=0;\s*i<n;\s*i\+\+\)")
    _, iw = q.match(r"PhotonWavelength\s*<=\s*\*\(wavelength\+\(i\+1\)\)")
    s = Source(root, "src/WCSimWCSD.cc", tag)
    rw = f"{tag} src/" + s.at(r"ratio\s*=\s*1\./\(1\.-0\.25\);")
    return dict(lo=float(m.group(1)), hi=float(m.group(2)),
                note=f"WCSim's rule ({cw}: 0 at or below {m.group(1)} and at or above {m.group(2)} nm; "
                f"{lw.split(':')[-1]}-{iw.split(':')[-1]}: linear over the first GetNbOfQEDefined + 1 knots, "
                "extrapolated below the first)",
                x43=f"{rw}")  # fmt: skip


def wcsim_qe(wl, qe, lo_cut, hi_cut):
    """Knots reproducing WCSimPMTQE's rule: linear, extrapolated below the first knot, 0 at or above hi_cut."""
    wl, qe = list(wl), list(qe)
    while wl[-1] > hi_cut:  # drop knots past the cut, keeping the interpolated value at the cut
        wl.pop(), qe.pop()
    if qe[0] > 0.0:  # WCSim extrapolates the first segment down to zero
        z = wl[0] - qe[0] * (wl[1] - wl[0]) / (qe[1] - qe[0])
        wl, qe = [max(z, lo_cut)] + wl, [0.0] + qe
    if qe[-1] > 0.0:
        wl, qe = wl + [wl[-1] + KNOT_STEP], qe + [0.0]
    return [round(x, 4) for x in wl], [round(x, 8) for x in qe]


def wcsim_sigma_knots(c, f, a, floor, q_lo):
    """Charge knots and WCSim's sigma(Q) = max(floor, f (a + sqrt(c / Q))) on them (Q >= q_lo), dense enough for 1e-3
    ns."""
    q_hi = c / (floor / f - a) ** 2
    q = np.unique(np.r_[np.geomspace(q_lo, q_hi, 96), q_hi])
    return q.round(6).tolist(), np.maximum(floor, f * (a + np.sqrt(c / q))).round(6).tolist()


def base(name, source, status, readout="hits"):
    return dict(
        schema="lumen-sensor-values/1",
        model="lumen:sensor",
        name=name,
        readout=readout,
        provenance=dict(source=source, status=status, fields={}, choices={}),
    )


def frontend(window, charge_noise, step):
    return dict(
        sampling_ns=1.0,
        unit="pe",
        baseline=0.0,
        noise=0.0,
        window_ns=window,
        charge_noise_pe=charge_noise,
        charge_scale=1.0,
        charge_step_pe=step,
        charge_max_pe=64.0,
    )


def ce_angles(src, cls):
    """WCSim's CE angle grid (WCSimPMTObject's default; no tube type here overrides it), whole degrees."""
    if src.has(f"{cls}::GetCollectionEfficiencyAngle"):
        raise ValueError(f"{cls} has its own CE angles: transcribe them")
    ang, where, _ = src.array("WCSimPMTObject::GetCollectionEfficiencyAngle()")
    if np.any(ang != np.round(ang)):
        raise ValueError(f"WCSim's CE angles are not whole degrees: {ang}")
    return [int(x) for x in ang], where


def qe_knots(src, cls, rule):
    """WCSim's QE knots of a tube type: the first GetNbOfQEDefined + 1 (WCSimPMTQE's loop reads knot i + 1, i < n)."""
    wl, w_where, _ = src.array(f"{cls}::GetQEWavelength()")
    qe, q_where, corr = src.array(f"{cls}::GetQE()")
    n = int(src.scalar(f"{cls}::GetNbOfQEDefined()", "factor"))
    kn, qv = wcsim_qe(wl[: n + 1], qe[: n + 1], rule["lo"], rule["hi"])
    used = min(n + 1, len(wl))
    nq = src.where(f"{cls}::GetNbOfQEDefined()")
    text = (f"{w_where}; {q_where}: the first {used} points (GetNbOfQEDefined = {n}; {nq}), without the correction "
            f"factor {corr} nor x4/3 (SensitiveDetector_Only, {rule['x43']}); {rule['note']}")  # fmt: skip
    return kn, qv, text


def sk_sets(w, d_ski, rule):
    src = w.pmt
    wl, w_where, _ = src.array("PMT20inch::GetQEWavelength()")
    qe, q_where, _ = src.array("PMT20inch::GetQE()")
    n = int(src.scalar("PMT20inch::GetNbOfQEDefined()", "factor"))
    kn, qv = wcsim_qe(wl[: n + 1], qe[: n + 1], rule["lo"], rule["hi"])
    ce, ce_where, _ = src.array("WCSimPMTObject::GetCollectionEfficiencyArray()")  # PMT20inch does not override it
    if src.has("PMT20inch::GetCollectionEfficiencyArray"):
        raise ValueError("PMT20inch has its own collection efficiency: transcribe it")
    ce = [float(x) / 100 for x in ce]
    angles, a_where = ce_angles(src, "PMT20inch")
    charge, c_where = w.spe("PMT20inch")
    rate, conv = src.scalar("PMT20inch::GetDarkRate()", "rate"), src.scalar("PMT20inch::GetDarkRateConversionFactor()",
                                                                             "factor")  # fmt: skip
    jit = w.jitter("PMT20inch")
    s1 = jitter_at(*jit[:4])
    d = base(
        "sk_r3600",
        f"{WCSIM_REF}: PMT20inch (src/WCSimPMTObject.cc) and the SKI digitizer " "(include/WCSimWCDigitizer.hh)",
        "transcribed",
    )
    d.update(qe=dict(wavelength_nm=kn, values=qv), ce=dict(theta_deg=angles, values=ce), efficiency=1.0,
             t_offset_ns=0.0, tts=dict(form="gaussian", sigma_ns=round(float(s1), 6)), charge=charge, gain=1.0,
             threshold=d_ski["threshold"], dark_rate_hz=round(rate * conv * 1e3, 6),
             frontend=frontend(d_ski["window"], d_ski["noise"], 1.0 / (2 * w.spe_scale)),
             ranges={"t_offset": [-10.0, 10.0]})  # fmt: skip
    d["provenance"]["fields"] = {
        "qe": f"{w_where}; {q_where}: physical QE, without SensitiveDetector_Only's x4/3 ({rule['x43']}); "
        f"{rule['note']}",
        "ce": f"{ce_where}: WCSimPMTObject::GetCollectionEfficiencyArray, {ce[0]:.0%} at every angle (PMT20inch does "
        "not override it; the 2011 table {100, 100, 99, 95, 90, 85, 80, 69, 35, 13} % was dropped in 2a3ff0adc6, "
        f'2015, "Different from SKDetSim"); angles {a_where}; WCSim\'s convention: theta = acos(z_local / r_local) '
        "about the PMT solid's origin",
        "tts": f"{jit[4]}: WCSim's per-digit smear {jitter_text(*jit[:4])} ns at Q = 1 pe, used as a "
        "per-photoelectron Gaussian (WCSim has no per-photoelectron time spread)",
        "charge": c_where,
        "threshold": d_ski["threshold_where"],
        "dark_rate_hz": f"{src.where('PMT20inch::GetDarkRate()')} x "
        f"{src.where('PMT20inch::GetDarkRateConversionFactor()')}",
        "frontend/window_ns": d_ski["window_where"],
        "frontend/charge_noise_pe": d_ski["noise_where"],
    }  # fmt: skip
    d["provenance"]["choices"] = choices(w.spe_scale)
    d["provenance"]["warning"] = ("timing unverified until transcribed: the per-photoelectron time spread is WCSim's "
                                  "per-digit smear at 1 pe (docs/explanation/known-limits.md)")  # fmt: skip
    return d, jit


def resolution_graph(src, spline):
    """WCTE's resolution graph: its knots (parsed) and ROOT's spline of it on the SPLINE_TXT charges, checked to pass
    through every knot in its range."""
    sig = "PMT3inchR14374_WCTE::PMT3inchR14374_WCTE()"
    qk, where, _ = src.array(sig, "charge[")
    rk, _, _ = src.array(sig, "resol[")
    q, r = np.loadtxt(spline, unpack=True)
    for x, y in zip(qk, rk, strict=True):
        hit = np.isclose(q, x, rtol=0, atol=1e-9)
        if hit.any() and not np.isclose(r[hit][0], y, rtol=0, atol=1e-9):
            raise ValueError(f"the spline text is not WCSim's graph at Q = {x}: {r[hit][0]} != {y}")
    return q, r, where


def wcte_sets(w, d_ski, rule, spline):
    src, cls = w.pmt, "PMT3inchR14374_WCTE"
    kn, qv, qe_text = qe_knots(src, cls, rule)
    ce, ce_where, _ = src.array(f"{cls}::GetCollectionEfficiencyArray()")
    angles, a_where = ce_angles(src, cls)
    charge, c_where = w.spe(cls)
    rate = src.scalar(f"{cls}::GetDarkRate()", "rate")
    conv = src.scalar(f"{cls}::GetDarkRateConversionFactor()", "factor")
    sig = f"{cls}::HitTimeSmearing("
    tts_fwhm = float(src.match(r"pmt_tts\s*=\s*([0-9.]+)", sig)[0].group(1))
    fwhm_sigma = float(src.match(r"/\s*([0-9.]+)\s*;", sig)[0].group(1))  # WCSim's FWHM-to-sigma conversion
    q, r, g_where = resolution_graph(src, spline)
    tw = dict(charge_pe=q.round(4).tolist(), shift_ns=[0.0] * len(q), sigma_ns=(r / fwhm_sigma).round(8).tolist())
    ts = src.where(sig)
    qmax = src.match(r"if\s*\(Q\s*>\s*([0-9.]+)\)", sig)[0].group(1)
    _, qmin = Source(src.path.parents[1], "src/WCSimWCDigitizer.cc", w.tag).match(
        r"double Q = \(peSmeared > ([0-9.]+)\) \? peSmeared : [0-9.]+;", SKI_DIGITIZE, same=True)  # fmt: skip
    d = base("wcte_r14374", f"{WCSIM_REF}: PMT3inchR14374_WCTE (src/WCSimPMTObject.cc) and the SKI "
             "digitizer", "transcribed")  # fmt: skip
    d.update(qe=dict(wavelength_nm=kn, values=qv), ce=dict(theta_deg=angles, values=[float(x) / 100 for x in ce]),
             efficiency=1.0, t_offset_ns=0.0, tts=dict(form="gaussian", sigma_ns=round(tts_fwhm / fwhm_sigma, 8)),
             time_walk=tw, charge=charge, gain=1.0, threshold=d_ski["threshold"],
             dark_rate_hz=round(rate * conv * 1e3, 6),
             frontend=frontend(d_ski["window"], d_ski["noise"], 1.0 / (2 * w.spe_scale)),
             ranges={"t_offset": [-10.0, 10.0]})  # fmt: skip
    d["provenance"]["fields"] = {
        "qe": qe_text,
        "ce": f"{ce_where}; angles {a_where}",
        "tts": f"{ts}: pmt_tts = {tts_fwhm} ns FWHM / {fwhm_sigma}",
        "time_walk": f"{ts}: the resolution graph R(min(Q, {qmax})) ({g_where}) / {fwhm_sigma}, ROOT's spline "
        f"evaluation on the SPLINE_TXT charges (checked at the graph's knots); sigma at max(Q, 0.5) ({qmin})",
        "charge": c_where,
        "threshold": d_ski["threshold_where"],
        "dark_rate_hz": f"{src.where(f'{cls}::GetDarkRate()')} x the conversion factor {conv} "
        f"({src.where(f'{cls}::GetDarkRateConversionFactor()')})",
        "frontend/window_ns": d_ski["window_where"],
        "frontend/charge_noise_pe": d_ski["noise_where"],
    }  # fmt: skip
    d["provenance"]["choices"] = choices(w.spe_scale) | {
        "time_walk/charge_pe": "the charges 0.5, 0.55, ..., 4 pe the spline is evaluated on (SPLINE_TXT)"
    }
    return d, (tts_fwhm, fwhm_sigma)


def hk_set(w, d_ski, rule, cls, name, tts, tts_note, tts_range, warning=None):
    """A Hyper-K / IWCD tube type of WCSim develop (BoxandLine20inchHQE, PMT3inchR14374, PMT3inchR12199_02)."""
    src = w.pmt
    kn, qv, qe_text = qe_knots(src, cls, rule)
    ce, ce_where, _ = src.array(f"{cls}::GetCollectionEfficiencyArray()")
    angles, a_where = ce_angles(src, cls)
    charge, c_where = w.spe(cls)
    rate = src.scalar(f"{cls}::GetDarkRate()", "rate")
    conv = src.scalar(f"{cls}::GetDarkRateConversionFactor()", "factor")
    unit = 1e-3 if "CLHEP::hertz" in src.function(f"{cls}::GetDarkRate()")[2] else 1.0  # kHz unless in hertz
    d = base(name, f"{WCSIM_REF}: {cls} (src/WCSimPMTObject.cc) and the SKI digitizer (include/WCSimWCDigitizer.hh)",
             "transcribed")  # fmt: skip
    d.update(qe=dict(wavelength_nm=kn, values=qv), ce=dict(theta_deg=angles, values=[float(x) / 100 for x in ce]),
             efficiency=1.0, t_offset_ns=0.0, tts=tts, charge=charge, gain=1.0, threshold=d_ski["threshold"],
             dark_rate_hz=round(rate * unit * conv * 1e3, 6),
             frontend=frontend(d_ski["window"], d_ski["noise"], 1.0 / (2 * w.spe_scale)),
             ranges={"tts/" + k: v for k, v in tts_range.items()} | {"t_offset": [-10.0, 10.0]})  # fmt: skip
    d["provenance"]["fields"] = {
        "qe": qe_text,
        "ce": f"{ce_where}; angles {a_where}",
        "tts": f"{src.where(f'{cls}::HitTimeSmearing(')}: {tts_note}",
        "charge": c_where,
        "threshold": d_ski["threshold_where"],
        "dark_rate_hz": f"{src.where(f'{cls}::GetDarkRate()')} x {src.where(f'{cls}::GetDarkRateConversionFactor()')}",
        "frontend/window_ns": d_ski["window_where"],
        "frontend/charge_noise_pe": d_ski["noise_where"],
    }  # fmt: skip
    d["provenance"]["choices"] = choices(w.spe_scale)
    if warning:
        d["provenance"]["warning"] = warning
    return d


def hk_sets(w, d_ski, rule):
    """The Hyper-K FD and IWCD tube types: 20-inch Box&Line, the HK mPMT's and OD's 3-inch R14374, IWCD's R12199-02."""
    src = w.pmt
    a, b, body = src.function("BoxandLine20inchHQE::HitTimeSmearing(")
    sp = [float(x) for x in re.search(r"sig_param\[4\]\s*=\s*\{([^}]*)\}", body).group(1).split(",")]
    lp = [float(x) for x in re.search(r"lambda_param\[2\]\s*=\s*\{([^}]*)\}", body).group(1).split(",")]
    shift = float(re.search(r"G4RandGauss::shoot\(([-0-9.]+),", body).group(1))
    if not 1.0 < sp[3]:
        raise ValueError("BoxandLine20inchHQE: Q = 1 pe is not on the low-charge branch")
    sig1 = sp[0] * (np.exp(-sp[1] * 1.0) + sp[2])  # Q = 1 pe < sig_param[3]: the low-charge branch
    tau1 = 1.0 / (lp[0] + lp[1] * 1.0)
    unverified = "timing unverified: WCSim's per-digit smear at 1 pe as a per-photoelectron spread"
    bl = hk_set(w, d_ski, rule, "BoxandLine20inchHQE", "wcsim_bl20_hqe",
                dict(form="emg", sigma_ns=round(float(sig1), 6), tau_ns=round(float(tau1), 6), shift_ns=shift),
                f"WCSim's per-digit smear at Q = 1 pe, N({shift}, sigma) + an exponential of mean 1 / lambda, sigma = "
                f"{sp[0]} (exp(-{sp[1]} Q) + {sp[2]}) (Q < {sp[3]}), lambda = {lp[0]} + {lp[1]} Q, used as a "
                "per-photoelectron exponentially modified Gaussian (WCSim has no per-photoelectron time spread)",
                {"tau": [0.5, 6.0], "shift": [-2.0, 2.0]}, warning=unverified)  # fmt: skip
    s14 = float(src.match(r"\bdouble\s+timingResolution\s*=\s*([0-9.]+)", "PMT3inchR14374::HitTimeSmearing(")[0]
                .group(1))  # fmt: skip
    note14 = (f"a {s14} ns Gaussian at every charge (WCSim's per-digit smear; TTSFF 1), used as the per-photoelectron "
              "spread")  # fmt: skip
    r14 = hk_set(w, d_ski, rule, "PMT3inchR14374", "wcsim_r14374", dict(form="gaussian", sigma_ns=s14), note14,
                 {})  # fmt: skip
    jit = w.jitter("PMT3inchR12199_02")
    s12 = jitter_at(*jit[:4])
    r12 = hk_set(w, d_ski, rule, "PMT3inchR12199_02", "wcsim_r12199_02",
                 dict(form="gaussian", sigma_ns=round(float(s12), 6)),
                 f"WCSim's per-digit smear {jitter_text(*jit[:4])} ns at Q = 1 pe, used as a per-photoelectron "
                 "Gaussian (WCSim has no per-photoelectron time spread)", {},
                 warning=unverified)  # fmt: skip
    od_s = float(src.match(r"\bdouble\s+timingResolution\s*=\s*([0-9.]+)", "PMT3inchR14374_FDOD::HitTimeSmearing(")
                 [0].group(1)) if src.has("PMT3inchR14374_FDOD::HitTimeSmearing(") else None  # fmt: skip
    if od_s is not None and od_s != s14:
        raise ValueError(f"PMT3inchR14374_FDOD's smear {od_s} differs from PMT3inchR14374's {s14}")
    od = hk_set(w, d_ski, rule, "PMT3inchR14374_FDOD", "wcsim_r14374_fdod", dict(form="gaussian", sigma_ns=s14),
                note14, {})  # fmt: skip
    return {d["name"]: d for d in (bl, r14, r12, od)}


ANNIE = {"R7081": "PMT_R7081", "D784KFLB": "PMT_D784KFLB", "R5912HQE": "PMT_R5912HQE", "R7081HQE": "PMT_R7081HQE"}


# the public sources the value sets are transcribed from: repository, full commit or tag, and URL
WCSIM_REF = (
    "WCSim develop e2dc7a48b1f83c74a541123542606a90d7b67a6f "
    "(https://github.com/WCSim/WCSim/tree/e2dc7a48b1f83c74a541123542606a90d7b67a6f)"
)


ANNIE_REF = (
    "WCSim annie e88314b31266255ed02a95ce87677f92d4c2db22 "
    "(https://github.com/ANNIEsoft/WCSim/tree/e88314b31266255ed02a95ce87677f92d4c2db22)"
)


def annie_run(root):
    """ANNIE's reference run settings in its WCSim tree: the tuning's QEratio and the digitizer's photon integration."""
    t = Source(root, "macros/tuning_parameters.mac", "WCSim annie")
    t.clean = [ln.split("#")[0] for ln in t.lines]
    m, qw = t.match(r"^/WCSim/tuning/QEratio\s+([0-9.]+)")
    daq = Source(root, "macros/annie_daq.mac", "WCSim annie")
    daq.clean = [ln.split("#")[0] for ln in daq.lines]
    i, iw = daq.match(r"^/DAQ/DigitizerOpt/DoPhotonIntegration\s+(\w+)")
    if i.group(1) != "false":
        raise ValueError("ANNIE's reference integrates photons: transcribe its window")
    _, tw = Source(root, "src/WCSimWCPMT.cc", "WCSim annie").match(r"time_PMT = time_true \+ PMT->HitTimeSmearing\(Q\)")
    return float(m.group(1)), qw, iw, tw


def annie_set(w, ty, run):
    src, cls = w.pmt, ANNIE[ty]
    ratio, ratio_where, integ_where, smear_where = run
    wl, w_where, _ = src.array(f"{cls}::GetQEWavelength()")
    qe, q_where, _ = src.array(f"{cls}::GetQE()")
    charge, c_where = w.spe(cls)
    rate = src.scalar(f"{cls}::GetDarkRate()", "rate")
    conv = src.scalar(f"{cls}::GetDarkRateConversionFactor()", "factor")
    jit = w.jitter(cls)
    s1 = jitter_at(*jit[:4])
    d = base(f"wcsim_annie_{ty}", f"{ANNIE_REF}: {cls} (src/WCSimPMTObject.cc); the SKI digitizer without "
             "photon integration or threshold (src/WCSimWCDigitizer.cc)", "transcribed")  # fmt: skip
    d.update(
        qe=dict(
            zip(
                ("wavelength_nm", "values"),
                cut_to_zero([float(x) for x in wl], [round(float(x) * ratio, 8) for x in qe]),
                strict=False,
            )
        ),
        ce=None,
        efficiency=1.0,
        t_offset_ns=0.0,
        tts=dict(form="gaussian", sigma_ns=round(float(s1), 6)),
        charge=charge,
        gain=1.0,
        threshold=None,
        dark_rate_hz=round(rate * conv * 1e3, 6),
        frontend=frontend(0.0, 0.0, 1.0 / (2 * w.spe_scale)),
        ranges={"t_offset": [-10.0, 10.0]},
    )
    no_int = f"0: each photoelectron its own hit, DoPhotonIntegration false ({integ_where})"
    d["provenance"]["fields"] = {
        "qe": f"{w_where}; {q_where}; times the tuning's QEratio {ratio} ({ratio_where}; Multi_Tank_Types: min(QE "
        "QEratio, maxQE_all QEratio), the cap never binding); 0 outside the table in WCSim, written as explicit zeros",
        "tts": f"{jit[4]}: {jitter_text(*jit[:4])} ns at Q = 1 pe as a per-photoelectron Gaussian (WCSim applies it "
        f"per photoelectron at that photoelectron's own charge, {smear_where})",
        "charge": c_where,
        "dark_rate_hz": f"{src.where(f'{cls}::GetDarkRate()')} x {conv}",
        "frontend/window_ns": no_int,
        "frontend/charge_noise_pe": f"{no_int}; no threshold, so none of its charge noise (the call is commented out "
        f"in WCSimWCDigitizer.cc)",
    }
    d["provenance"]["choices"] = choices(w.spe_scale)
    d["provenance"]["warning"] = "timing unverified: WCSim's per-photoelectron smear at 1 pe"
    return d, jit


def emulation(d, jit=None, tw=None, scale=None, q_lo=None):
    """A WCSim-emulating test set: no per-photoelectron spread, WCSim's per-digit smear as the time walk."""
    e = json.loads(json.dumps(d))
    e["name"] = d["name"] + "_wcsim_emulation"
    e["provenance"] = dict(
        source=d["provenance"]["source"],
        status="transcribed",
        note="test reference only: WCSim's conventions (0.985, per-digit smear), not physical",
    )
    e["tts"] = dict(form="gaussian", sigma_ns=0.0)
    if jit is not None:
        q, s = wcsim_sigma_knots(*jit[:4], q_lo)
        e["time_walk"] = dict(charge_pe=q, shift_ns=[0.0] * len(q), sigma_ns=s)
    if tw is not None:
        e["time_walk"] = tw
    e["frontend"]["charge_scale"] = scale
    return e


def digitizer_conventions(root, tag):
    """WCSim's charge factor (WCSimWCDigitizer.cc) and the smear's lowest charge, for the emulating sets."""
    s = Source(root, "src/WCSimWCDigitizer.cc", tag)
    eff = float(s.match(r"G4double efficiency = ([0-9.]+);", SKI_DIGITIZE)[0].group(1))
    q_lo = float(
        s.match(r"double Q = \(peSmeared > ([0-9.]+)\) \? peSmeared : [0-9.]+;", SKI_DIGITIZE, same=True)[0].group(1)
    )
    return eff, q_lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wcsim", required=True)
    ap.add_argument("--annie")
    ap.add_argument("--spline")
    ap.add_argument("--out")
    ap.add_argument("--tests")
    ap.add_argument("--only", help="comma-separated value sets to write (e.g. the HK sets; needs only --wcsim)")
    a = ap.parse_args()
    w = Wcsim(a.wcsim, "WCSim")
    d_ski, rule = ski(w), qe_rule(a.wcsim, "WCSim")
    if a.only:
        sets = hk_sets(w, d_ski, rule)
        for name in a.only.split(","):
            d = datasheet_qe(sets[name])
            (Path(a.out) / f"{name}.json").write_text(json.dumps(d, indent=1) + "\n")
        print("wrote", a.only)
        return
    aw = Wcsim(a.annie, "WCSim annie")
    run = annie_run(a.annie)
    scale, q_lo = digitizer_conventions(a.wcsim, "WCSim")
    out, tests = Path(a.out), Path(a.tests)
    out.mkdir(parents=True, exist_ok=True)
    tests.mkdir(parents=True, exist_ok=True)
    sk, sk_jit = sk_sets(w, d_ski, rule)
    wcte, (tts_fwhm, fwhm_sigma) = wcte_sets(w, d_ski, rule, a.spline)
    sets = {"sk_r3600": sk, "wcte_r14374": wcte}
    emu = {"sk": emulation(sk, jit=sk_jit, scale=scale, q_lo=q_lo)}
    tw = dict(wcte["time_walk"])
    tw["sigma_ns"] = (
        (np.sqrt(tts_fwhm**2 + (np.asarray(tw["sigma_ns"]) * fwhm_sigma) ** 2) / fwhm_sigma).round(8).tolist()
    )
    emu["wcte"] = emulation(wcte, tw=tw, scale=scale)
    for ty in ANNIE:
        d, jit = annie_set(aw, ty, run)
        sets[d["name"]] = d
        emu[f"annie_{ty}"] = emulation(d, jit=jit, scale=scale, q_lo=q_lo)
    sets.update(hk_sets(w, d_ski, rule))
    for name in WCSIM_SETS:
        sets[name] = datasheet_qe(sets[name])
    for name, d in sets.items():
        (out / f"{name}.json").write_text(json.dumps(d, indent=1) + "\n")
    for name, d in emu.items():
        (tests / f"{name}.json").write_text(json.dumps(d, indent=1) + "\n")
    print("wrote", sorted(sets), "and", sorted(emu))


if __name__ == "__main__":
    main()
