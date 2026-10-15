"""Clash geometry.

Every element is an axis-aligned box ``lo..hi`` (a straight pipe or duct run is a box of
zero thickness, i.e. a segment) inflated by a radius.  The surface gap between two
elements is ``|gap of the boxes| - r1 - r2``, which is exact for boxes and for straight
axis-aligned runs (end caps are treated as hemispheres).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

EPS = 1e-9


@dataclass(frozen=True)
class Solid:
    eid: str            # element id, e.g. "C-03-02", "PCWS-A", "HU-N03-CDA#2"
    kind: str           # column | header | equipment | route
    lo: tuple
    hi: tuple
    r: float = 0.0
    owner: str = ""     # hookup id for route runs, header id for headers
    meta: dict = field(default_factory=dict, compare=False, hash=False)


def box_gap(lo1, hi1, lo2, hi2) -> float:
    s = 0.0
    for a in range(3):
        g = max(0.0, lo2[a] - hi1[a], lo1[a] - hi2[a])
        s += g * g
    return math.sqrt(s)


def surface_gap(a: Solid, b: Solid) -> float:
    return box_gap(a.lo, a.hi, b.lo, b.hi) - a.r - b.r


def segment_solid(eid, p, q, r, owner, kind="route", meta=None) -> Solid:
    if sum(1 for a in range(3) if abs(p[a] - q[a]) > EPS) > 1:
        raise ValueError(f"{eid}: run {p}->{q} is not axis-aligned")
    lo = tuple(min(p[a], q[a]) for a in range(3))
    hi = tuple(max(p[a], q[a]) for a in range(3))
    return Solid(eid, kind, lo, hi, r, owner, meta or {})


def polyline_solids(hookup_id: str, pts: list, r: float, meta=None) -> list[Solid]:
    return [segment_solid(f"{hookup_id}#{n}", pts[n], pts[n + 1], r, hookup_id, meta=meta)
            for n in range(len(pts) - 1)]


def node_gap_field(X, Y, Z, s: Solid):
    """Surface gap from every lattice node (as a point) to solid ``s``."""
    gx = np.maximum(0.0, np.maximum(s.lo[0] - X, X - s.hi[0]))
    gy = np.maximum(0.0, np.maximum(s.lo[1] - Y, Y - s.hi[1]))
    gz = np.maximum(0.0, np.maximum(s.lo[2] - Z, Z - s.hi[2]))
    return np.sqrt(gx * gx + gy * gy + gz * gz) - s.r


def find_clashes(new: list[Solid], existing: list[Solid], clearance: float,
                 exempt=lambda a, b: False) -> list[dict]:
    """Clashes of ``new`` runs against ``existing`` elements and against each other.

    hard      : solids overlap (gap < 0)
    clearance : gap below the clearance but not overlapping
    Runs of the same hookup are never tested against each other.
    """
    out = []
    cands = existing + new
    nlo = np.array([c.lo for c in cands], dtype=float).reshape(-1, 3)
    nhi = np.array([c.hi for c in cands], dtype=float).reshape(-1, 3)
    nr = np.array([c.r for c in cands], dtype=float)
    n_exist = len(existing)
    for idx, a in enumerate(new):
        gap3 = np.maximum(0.0, np.maximum(nlo - np.array(a.hi), np.array(a.lo) - nhi))
        gaps = np.sqrt((gap3 * gap3).sum(axis=1)) - a.r - nr
        hits = np.nonzero(gaps < clearance - EPS)[0]
        for h in hits:
            h = int(h)
            if h >= n_exist and h - n_exist <= idx:
                continue   # each new/new pair once
            b = cands[h]
            if b.kind == "route" and b.owner == a.owner:
                continue
            if exempt(a, b):
                continue
            g = float(gaps[h])
            out.append({"a": a.eid, "b": b.eid, "b_kind": b.kind, "gap_m": g,
                        "type": "hard" if g < -EPS else "clearance"})
    out.sort(key=lambda d: (d["a"], d["b"]))
    return out
