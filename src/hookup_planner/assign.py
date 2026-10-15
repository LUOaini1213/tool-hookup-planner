"""POC assignment: MILP (scipy/HiGHS) with header capacity, header upgrade steps and new POCs.

Decision variables
  x[r,p]  requirement r (tool x utility) connects to POC p                 binary
          p is either an existing free POC or a *potential new POC* (a new take-off position
          on a header between existing POCs, sized for r, with an illustrative fixed cost;
          process lateral work, made however the utility requires)
  y[h]    capacity upgrade steps on header h (process lateral work)        integer 0..Y_MAX
  u[r]    requirement left unserved (penalty)                              binary
Objective  sum (rate_m x est_length + new-POC cost) x  +  sum C_h y_h  +  BIG u
Subject to sum_p x[r,p] + u[r] = 1;  sum_r x[r,p] <= 1;
           sum_{p on h} demand_r x[r,p] - step_h y_h <= remaining_h;
           PCW pairing: for every tool with PCW supply s and return t and every corridor c,
           sum_{p in c} x[s,p] - sum_{p in c} x[t,p] = 0  (supply and return on one corridor).
Estimated length = take-off stub + obstacle-aware BFS distance + floor riser.  A tiny
index-based perturbation makes the optimum unique, so the result does not depend on the
solver's tie-breaking (and is identical on every platform).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import lil_matrix

from . import engineering as E
from . import hydraulics as H
from .model import Index, header_loads

Y_MAX = 5
EPS_TIE = 1e-6


def potential_new_pocs(site: dict, lat, system: str) -> list[dict]:
    """New take-off positions half-way between the existing POCs of every header of ``system``."""
    out = []
    taken = {(p["header"], round(p["x"] / lat.step)) for p in site["pocs"]}
    for h in sorted(site["headers"], key=lambda h: h["id"]):
        if h["system"] != system:
            continue
        i0, i1 = round(h["x0"] / lat.step), round(h["x1"] / lat.step)
        for i in range(i0 + 1, i1):
            if i % 6 == 0 and (h["id"], i) not in taken:
                out.append({"id": f"{h['id']}-N{i:03d}", "header": h["id"], "system": system,
                            "x": round(i * lat.step, 9), "y": h["y"], "z": h["z"]})
    return out


def candidates(site: dict, lat, reqs: list[dict]) -> tuple[dict, dict]:
    """Feasible (requirement, POC) pairs -> estimated hookup length (m), plus new-POC specs."""
    idx = Index(site)
    used = {hk["poc"] for hk in site["hookups"]}
    step = lat.step
    riser = E.FAB_FLOOR_Z - (lat.kmax + 1) * step
    cand, newpocs = {}, {}
    for r, d in enumerate(reqs):
        hdr_p = next(h["pressure_kpa_g"] for h in site["headers"] if h["system"] == d["system"])
        prov = H.min_size_velocity(d["system"], d["flow"], hdr_p)
        cand[r] = {}
        if prov is None:
            continue
        rad = prov["od"] / 2
        goal = lat.snap(d["px"], d["py"], (lat.kmax + 1) * step)
        free = lat.free_mask(rad, E.CLEARANCE_M, goal)
        dist = lat.bfs_from_goal(free, goal)
        pocs = [p for p in site["pocs"] if p["system"] == d["system"] and p["status"] == "free"
                and p["id"] not in used and p["rated_flow"] >= d["flow"]]
        for p in pocs + potential_new_pocs(site, lat, d["system"]):
            stub = lat.stub(p["header"], lat.snap(p["x"], p["y"], p["z"]), rad, E.CLEARANCE_M)
            if stub is None or stub[-1] not in dist:
                continue
            key = p["id"] if p["id"] in idx.pocs else f"{p['id']}@{r}"
            cand[r][key] = (len(stub) - 1) * step + dist[stub[-1]] * step + riser
            if key not in idx.pocs:
                newpocs[key] = dict(p, size=prov["label"], requirement=r)
    return cand, newpocs


def position(pid: str) -> str:
    """Physical position of a candidate (new-POC candidates are per requirement)."""
    return pid.split("@")[0]


def pair_cost(reqs, cand, rates, r, p) -> float:
    c = rates["assignment_cost_per_m"][reqs[r]["system"]] * cand[r][p]
    return c + (rates["new_poc_each"] if "@" in p else 0.0)


def _remaining(site: dict, reserve: float) -> dict:
    loads = header_loads(site)
    return {h["id"]: h["capacity"] * (1.0 - reserve) - loads[h["id"]] for h in site["headers"]}


def _header_of(site, newpocs, p):
    return newpocs[p]["header"] if p in newpocs else Index(site).pocs[p]["header"]


def pcw_pairs(reqs: list[dict]) -> list[tuple[int, int]]:
    """(supply requirement, return requirement) for every tool that has both PCW connections."""
    by_tool: dict[str, dict] = {}
    for r, d in enumerate(reqs):
        if d["system"] in E.PCW_PAIR:
            by_tool.setdefault(d["tool"], {})[d["system"]] = r
    return sorted((v[E.PCW_PAIR[0]], v[E.PCW_PAIR[1]]) for v in by_tool.values() if len(v) == 2)


def corridor(site: dict, newpocs: dict, p: str) -> str:
    return Index(site).headers[_header_of(site, newpocs, p)]["corridor"]


def solve(site: dict, reqs: list[dict], cand: dict, newpocs: dict, rates: dict, reserve: float = 0.0,
          capacity: bool = True, allow_new: bool = True, pairing: bool = True) -> dict:
    idx = Index(site)
    rem = _remaining(site, reserve)
    big = 100.0 * rates["new_poc_each"] + 1e6
    pairs = [(r, p) for r in range(len(reqs)) for p in sorted(cand[r]) if allow_new or "@" not in p]
    hdrs = sorted(h["id"] for h in site["headers"]) if capacity else []
    positions = sorted({position(p) for _, p in pairs})
    corr = {(r, p): corridor(site, newpocs, p) for r, p in pairs if reqs[r]["system"] in E.PCW_PAIR}
    pair_rows = []                       # (supply r, return r, corridor)
    if pairing:
        for s, t in pcw_pairs(reqs):
            for c_ in sorted({corr[(r, p)] for r, p in pairs if r in (s, t)}):
                pair_rows.append((s, t, c_))
    nx_, nh, nr = len(pairs), len(hdrs), len(reqs)
    nvar = nx_ + nh + nr
    c = np.zeros(nvar)
    for n, (r, p) in enumerate(pairs):
        c[n] = pair_cost(reqs, cand, rates, r, p) + EPS_TIE * (n + 1)
    for n, h in enumerate(hdrs):
        c[nx_ + n] = idx.headers[h]["upgrade_cost"] + EPS_TIE * (nx_ + n + 1)
    c[nx_ + nh:] = big
    rows = nr + len(positions) + nh + len(pair_rows)
    A = lil_matrix((rows, nvar))
    lb = np.full(rows, -np.inf)
    ub = np.zeros(rows)
    row0 = nr + len(positions) + nh
    for k, (s, t, c_) in enumerate(pair_rows):
        lb[row0 + k] = ub[row0 + k] = 0.0
        for n, (r, p) in enumerate(pairs):
            if (r, p) in corr and corr[(r, p)] == c_:
                if r == s:
                    A[row0 + k, n] = 1.0
                elif r == t:
                    A[row0 + k, n] = -1.0
    for r in range(nr):
        A[r, nx_ + nh + r] = 1.0
        lb[r] = ub[r] = 1.0
    prow = {p: nr + n for n, p in enumerate(positions)}
    for p in positions:
        ub[prow[p]] = 1.0
    hrow = {h: nr + len(positions) + n for n, h in enumerate(hdrs)}
    for n, h in enumerate(hdrs):
        A[hrow[h], nx_ + n] = -idx.headers[h]["upgrade_step"]
        ub[hrow[h]] = rem[h]
    for n, (r, p) in enumerate(pairs):
        A[r, n] = 1.0
        A[prow[position(p)], n] = 1.0
        if capacity:
            d = reqs[r]
            A[hrow[_header_of(site, newpocs, p)], n] = d["flow"] * E.COINCIDENCE_FACTOR[d["system"]]
    hi = np.ones(nvar)
    hi[nx_:nx_ + nh] = Y_MAX
    res = milp(c, integrality=np.ones(nvar), bounds=Bounds(np.zeros(nvar), hi),
               constraints=LinearConstraint(A.tocsr(), lb, ub), options={"mip_rel_gap": 0.0, "disp": False})
    if res.x is None:
        raise RuntimeError(f"MILP failed: {res.message}")
    x = np.round(res.x).astype(int)
    assign = {r: p for n, (r, p) in enumerate(pairs) if x[n]}
    upgrades = {h: int(x[nx_ + n]) for n, h in enumerate(hdrs) if x[nx_ + n]}
    unassigned = [r for r in range(nr) if x[nx_ + nh + r]]
    return summary(site, reqs, cand, newpocs, rates, assign, upgrades, unassigned,
                   {(True, True): "milp", (False, False): "milp_relaxed", (True, False): "milp_no_pairing",
                    (False, True): "milp_no_capacity"}[(capacity, pairing)])


def summary(site, reqs, cand, newpocs, rates, assign, upgrades, unassigned, method) -> dict:
    idx = Index(site)
    hook = sum(pair_cost(reqs, cand, rates, r, p) for r, p in assign.items())
    up_cost = sum(idx.headers[h]["upgrade_cost"] * n for h, n in upgrades.items())
    return {"method": method, "assign": {r: assign[r] for r in sorted(assign)},
            "upgrades": dict(sorted(upgrades.items())), "unassigned": unassigned,
            "new_pocs": sorted(p for p in assign.values() if "@" in p),
            "est_length_m": sum(cand[r][p] for r, p in assign.items()),
            "est_hookup_cost": hook, "upgrade_cost": up_cost, "objective": hook + up_cost}


def greedy(site: dict, reqs: list[dict], cand: dict, newpocs: dict, rates: dict, reserve: float = 0.0) -> dict:
    """Baseline: requirements in list order take their cheapest free POC; upgrade that header if short.

    A PCW return is restricted to the corridor of its tool's supply (assigned earlier in the
    list), so the baseline obeys the same pairing rule as the MILP.
    """
    idx = Index(site)
    rem = _remaining(site, reserve)
    taken, assign, upgrades, unassigned = set(), {}, {}, []
    supply_of = {t: s for s, t in pcw_pairs(reqs)}
    for r, d in enumerate(reqs):
        opts = sorted((pair_cost(reqs, cand, rates, r, p), p) for p in cand[r] if position(p) not in taken)
        if r in supply_of:
            s = supply_of[r]
            want = corridor(site, newpocs, assign[s]) if s in assign else None
            opts = [o for o in opts if corridor(site, newpocs, o[1]) == want]
        if not opts:
            unassigned.append(r)
            continue
        p = opts[0][1]
        h = _header_of(site, newpocs, p)
        load = d["flow"] * E.COINCIDENCE_FACTOR[d["system"]]
        while rem[h] < load:
            rem[h] += idx.headers[h]["upgrade_step"]
            upgrades[h] = upgrades.get(h, 0) + 1
        rem[h] -= load
        taken.add(position(p))
        assign[r] = p
    return summary(site, reqs, cand, newpocs, rates, assign, upgrades, unassigned, "greedy")


def hungarian(site: dict, reqs: list[dict], cand: dict, newpocs: dict, rates: dict) -> dict:
    """Cross-check of the relaxed problem (no capacity, no PCW pairing) with linear_sum_assignment.

    Columns are physical positions; a new-POC position is priced per requirement.
    """
    positions = sorted({position(p) for r in cand for p in cand[r]})
    col = {p: n for n, p in enumerate(positions)}
    big = 1e12
    M = np.full((len(reqs), len(positions)), big)
    best = {}
    for r in cand:
        for p in cand[r]:
            c = pair_cost(reqs, cand, rates, r, p)
            if c < M[r, col[position(p)]]:
                M[r, col[position(p)]] = c
                best[(r, position(p))] = p
    rows, cols = linear_sum_assignment(M)
    assign = {int(r): best[(int(r), positions[c])] for r, c in zip(rows, cols) if M[r, c] < big}
    unassigned = [r for r in range(len(reqs)) if r not in assign]
    return summary(site, reqs, cand, newpocs, rates, assign, {}, unassigned, "hungarian_relaxed")
