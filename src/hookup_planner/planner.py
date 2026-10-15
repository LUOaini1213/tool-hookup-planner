"""End-to-end hookup planning: capacity check -> assignment -> A* routing -> sizing -> clashes."""
from __future__ import annotations

import copy

from . import assign as A
from . import engineering as E
from .capacity import capacity_check, new_demand
from .geometry import Solid, find_clashes
from .lattice import compress, length
from .model import Index, as_built, build_lattice, hookup_solids, route_one, static_solids, tool_side_pressure
from .scenario import rated_flow

KIND_ORDER = {"exhaust": 0, "liquid": 1, "gas": 2, "power": 3}


def route_order(reqs: list[dict]) -> list[int]:
    """Bulky ducts first, then pipes, then cables; larger flows first within a system."""
    return sorted(range(len(reqs)), key=lambda r: (KIND_ORDER[E.SYSTEMS[reqs[r]["system"]]["kind"]],
                                                   E.SYSTEM_ORDER.index(reqs[r]["system"]),
                                                   -reqs[r]["flow"], reqs[r]["tool"]))


def hookup_id(d: dict) -> str:
    return f"HN-{d['tool'][2:]}-{d['system']}"


def naive_points(poc: dict, d: dict, kmax_z: float) -> list:
    """Manhattan L-route ignoring obstacles: up, along x, along y, up to the floor."""
    pts = [(poc["x"], poc["y"], poc["z"]), (poc["x"], poc["y"], kmax_z), (d["px"], poc["y"], kmax_z),
           (d["px"], d["py"], kmax_z), (d["px"], d["py"], E.FAB_FLOOR_Z)]
    dedup = [pts[0]]
    for p in pts[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    return compress(dedup)


def own_header_exempt(site: dict):
    poc_header = {p["id"]: p["header"] for p in site["pocs"]}

    def exempt(a: Solid, b: Solid) -> bool:
        # the first run of a hookup is its take-off, which starts on its own header's axis
        return b.kind == "header" and a.eid.endswith("#0") and poc_header.get(a.meta.get("poc")) == b.eid
    return exempt


def materialise_poc(site_w: dict, newpocs: dict, key: str) -> dict:
    """Add a chosen potential new POC to the working site (status 'planned')."""
    pid = A.position(key)
    idx = Index(site_w)
    if pid in idx.pocs:
        return idx.pocs[pid]
    spec = newpocs[key]
    hp = idx.headers[spec["header"]]["pressure_kpa_g"]
    poc = {"id": pid, "header": spec["header"], "system": spec["system"], "x": spec["x"], "y": spec["y"],
           "z": spec["z"], "size": spec["size"], "rated_flow": rated_flow(spec["system"], spec["size"], hp),
           "status": "planned"}
    site_w["pocs"].append(poc)
    return poc


def reserve_takeoffs(lat, site_w: dict, reqs: list[dict], chosen: dict, newpocs: dict) -> list[int]:
    """Keep every chosen take-off column clear for its own hookup; returns the reserved nodes."""
    idx = Index(site_w)
    out = []
    for r, key in sorted(chosen.items()):
        p = newpocs[key] if key in newpocs else idx.pocs[key]
        d = reqs[r]
        prov = A.H.min_size_velocity(d["system"], d["flow"], idx.headers[p["header"]]["pressure_kpa_g"])
        stub = lat.stub(p["header"], lat.snap(p["x"], p["y"], p["z"]), prov["od"] / 2, E.CLEARANCE_M)
        for n in (stub or [])[1:]:
            lat.reserved[n] = True
            out.append(n)
    return out


def plan(site: dict, rates: dict, reserve: float = 0.0, tools: list[str] | None = None) -> dict:
    site_w = copy.deepcopy(as_built(site))
    reqs = new_demand(site_w, tools)
    cap = capacity_check(site_w, tools, reserve)
    lat = build_lattice(site_w)
    cand, newpocs = A.candidates(site_w, lat, reqs)
    res = {"milp": A.solve(site_w, reqs, cand, newpocs, rates, reserve),
           "milp_existing_pocs_only": A.solve(site_w, reqs, cand, newpocs, rates, reserve, allow_new=False),
           "milp_no_pairing": A.solve(site_w, reqs, cand, newpocs, rates, reserve, pairing=False),
           "greedy": A.greedy(site_w, reqs, cand, newpocs, rates, reserve),
           "milp_relaxed": A.solve(site_w, reqs, cand, newpocs, rates, reserve, capacity=False, pairing=False),
           "hungarian_relaxed": A.hungarian(site_w, reqs, cand, newpocs, rates)}
    chosen = dict(res["milp"]["assign"])

    reserve_takeoffs(lat, site_w, reqs, chosen, newpocs)

    hookups, failures, reassigned = [], [], []
    taken = {A.position(k) for k in chosen.values()}
    supply: dict[str, tuple] = {}     # tool -> (PCWS header pressure, PCWS hookup loss, corridor)
    for r in route_order(reqs):
        d = reqs[r]
        if r not in chosen:
            failures.append({"tool": d["tool"], "system": d["system"], "reason": "no POC assigned"})
            continue
        if d["system"] == E.PCW_PAIR[1] and d["tool"] not in supply:
            failures.append({"tool": d["tool"], "system": d["system"], "reason": "PCW supply not routed"})
            continue
        tool_p = tool_side_pressure(d["system"], d["p_req"], supply.get(d["tool"]))
        tries = [chosen[r]] + [k for _, k in sorted((A.pair_cost(reqs, cand, rates, r, k), k) for k in cand[r])
                               if A.position(k) not in taken]
        if d["system"] == E.PCW_PAIR[1]:
            tries = [k for k in tries if A.corridor(site_w, newpocs, k) == supply[d["tool"]][2]]
        out = None
        for key in tries[:6]:
            poc = materialise_poc(site_w, newpocs, key) if key in newpocs else Index(site_w).pocs[key]
            out = route_one(site_w, lat, d["system"], d["flow"], tool_p, poc, (d["px"], d["py"]))
            if "error" not in out:
                if key != chosen[r]:
                    reassigned.append({"tool": d["tool"], "system": d["system"], "from": chosen[r], "to": key})
                    taken.add(A.position(key))
                    chosen[r] = key
                break
            if key in newpocs and key != chosen[r]:
                site_w["pocs"] = [p for p in site_w["pocs"] if p["id"] != A.position(key)]
        if out is None or "error" in out:
            failures.append({"tool": d["tool"], "system": d["system"], "reason": out["error"] if out else "none"})
            continue
        ev = out["eval"]
        hdr = Index(site_w).headers[poc["header"]]
        if d["system"] == E.PCW_PAIR[0]:
            supply[d["tool"]] = (hdr["pressure_kpa_g"], ev["dp_total_kpa"], hdr["corridor"])
        hk = {"id": hookup_id(d), "tool": d["tool"], "system": d["system"], "poc": poc["id"],
              "header": poc["header"], "corridor": hdr["corridor"], "new_poc": poc["status"] == "planned",
              "status": "planned",
              "size": out["size"], "points": [list(p) for p in out["points"]], "length_m": length(out["points"]),
              "bends": len(out["points"]) - 2, "est_length_m": cand[r][chosen[r]],
              "flow": d["flow"], "p_req": d["p_req"], "tool_p_kpa_g": tool_p, "governed_by": out["governed_by"],
              "velocity": ev["velocity"], "dp_total_kpa": ev["dp_total_kpa"],
              "dp_friction_kpa": ev.get("dp_friction_kpa"), "dp_fittings_kpa": ev.get("dp_minor_kpa"),
              "dp_static_kpa": ev.get("dp_static_kpa"), "design_current_a": ev.get("design_current_a"),
              "available_dp_kpa": ev["available_dp_kpa"], "regime": ev["regime"],
              "pressure_ok": ev["pressure_ok"], "velocity_ok": ev["velocity_ok"], "valid_model": ev["valid_model"]}
        hookups.append(hk)
        lat.add_route(hookup_solids(hk))
    hookups.sort(key=lambda h: h["id"])
    used_new = {hk["poc"] for hk in hookups if hk["new_poc"]}
    site_w["pocs"] = [p for p in site_w["pocs"] if p["status"] != "planned" or p["id"] in used_new]

    existing = static_solids(site_w) + [s for hk in site_w["hookups"] for s in hookup_solids(hk)]
    exempt = own_header_exempt(site_w)
    clashes = find_clashes([s for hk in hookups for s in hookup_solids(hk)], existing, E.CLEARANCE_M, exempt)

    idx = Index(site_w)
    naive = []
    for hk in hookups:
        d = idx.demand[(hk["tool"], hk["system"])]
        pts = naive_points(idx.pocs[hk["poc"]], d, lat.kmax * lat.step)
        naive.append({"id": hk["id"], "tool": hk["tool"], "system": hk["system"], "poc": hk["poc"],
                      "size": hk["size"], "points": [list(p) for p in pts]})
    naive_clashes = find_clashes([s for hk in naive for s in hookup_solids(hk)], existing, E.CLEARANCE_M, exempt)

    return {"site": site_w, "requirements": reqs, "capacity": cap, "candidates": cand, "new_poc_specs": newpocs,
            "assignment": res, "hookups": hookups, "failures": failures, "reassigned": reassigned,
            "clashes": clashes, "naive": naive, "naive_clashes": naive_clashes,
            "lower_bound_length_m": sum(length([tuple(p) for p in n["points"]]) for n in naive)}
