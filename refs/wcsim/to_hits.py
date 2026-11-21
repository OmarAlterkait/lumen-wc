"""dump_hits.C output -> the common hits format (refs/README.md; g4ref's own, read by validation/wave_cmp.py):
chunk<k>_hits.npy (src, evt, sensor, t [ns], E [eV]), chunk<k>_sensors.csv (sensor, path, lv, cx_mm, cy_mm, cz_mm,
dx, dy, dz: WCSim's tube tables), chunk<k>_summary.txt (launched photons per source: events x BATCH).
    python3 to_hits.py OUTDIR K BATCH CONFIG
HK copy: every collection dump_hits.C wrote (set 0 ID, 1 hybrid mPMTs, 2 OD), each in its own tube-id space. Sensor ids
are consecutive over the sets in that order (sensor = offset(set) + tube - 1); the path is "<set name>:tube<tube - 1>"
and the lv column the set name (wcsim_id, wcsim_mpmt, wcsim_od), which the charge check groups by."""

import glob
import os
import re
import sys

import numpy as np

SETS = ("wcsim_id", "wcsim_mpmt", "wcsim_od")
OUT, K, BATCH, CFG = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
files = sorted(
    glob.glob(os.path.join(OUT, f"chunk{K}_s*_hits.csv")), key=lambda f: int(re.search(r"_s(\d+)_hits", f).group(1))
)
cfg = np.loadtxt(CFG, comments="#", ndmin=2)
rows, launched, tubes = [], {}, None
for f in files:
    s = int(re.search(r"_s(\d+)_hits", f).group(1))
    h = np.loadtxt(f, delimiter=",", skiprows=1, ndmin=2)
    log = open(f.replace("_hits.csv", "_dump.log")).read()
    nev = int(re.search(r"dump_hits: (\d+) events", log).group(1))
    launched[s] = nev * BATCH
    if len(h):
        rows.append(np.c_[np.full(len(h), s), h])
    t = np.loadtxt(f.replace("_hits.csv", "_tubes.csv"), delimiter=",", skiprows=1, ndmin=2)
    if tubes is None:
        tubes = t
    elif not np.array_equal(t, tubes):
        raise SystemExit(f"{f}: a tube table differing from the chunk's first")
offset = {}
for st in range(len(SETS)):
    sel = tubes[:, 0] == st
    if sel.any():
        if not np.array_equal(np.sort(tubes[sel, 1]), np.arange(1, sel.sum() + 1)):
            raise SystemExit(f"set {st}: tube numbers are not 1..{sel.sum()}")
        offset[st] = sum(int((tubes[:, 0] == q).sum()) for q in range(st))
dt = np.dtype([("src", "<i4"), ("evt", "<i4"), ("sensor", "<i4"), ("t", "<f4"), ("E", "<f4")])
a = np.concatenate(rows) if rows else np.zeros((0, 5))  # src, set, evt, tube, t
hits = np.zeros(len(a), dt)
off = np.array([offset.get(st, -1) for st in range(len(SETS))])
if len(a) and np.any(off[a[:, 1].astype(int)] < 0):
    raise SystemExit("a hit in a set without a tube table")
hits["src"], hits["evt"], hits["t"] = a[:, 0], a[:, 2], a[:, 4]
hits["sensor"] = off[a[:, 1].astype(int)] + a[:, 3].astype(int) - 1
hits["E"] = cfg[hits["src"], 4]
np.save(os.path.join(OUT, f"chunk{K}_hits.npy"), hits)
with open(os.path.join(OUT, f"chunk{K}_sensors.csv"), "w") as fo:
    fo.write("sensor,path,lv,cx_mm,cy_mm,cz_mm,dx,dy,dz\n")
    for st, tb, x, y, z, dx, dy, dz, *_ in sorted(tubes.tolist(), key=lambda r: (r[0], r[1])):
        sid = offset[int(st)] + int(tb) - 1
        fo.write(
            f"{sid},{SETS[int(st)]}:tube{int(tb) - 1},{SETS[int(st)]},{x * 10:.4f},{y * 10:.4f},{z * 10:.4f},"
            f"{dx:.6f},{dy:.6f},{dz:.6f}\n"
        )
with open(os.path.join(OUT, f"chunk{K}_summary.txt"), "w") as fo:
    fo.write("source launched\n")
    for s in sorted(launched):
        fo.write(f"{s} {launched[s]}\n")
per = {SETS[st]: int((a[:, 1] == st).sum()) for st in offset}
print(f"chunk {K}: {len(hits)} hits {per} from {len(files)} sources; launched {launched}; {len(tubes)} tubes")
