"""Drawing review aid: automated checks of a hookup proposal against the utilities model.

A proposal is a list of hookups {id, tool, system, poc, size, points} plus the header
upgrade steps it relies on ({header: steps}).  The review recomputes everything from the
proposal's own geometry and the site model; it does not trust numbers in the proposal.
It reuses the planner's hydraulic and clash functions, so it is not an independent check
of those formulas.
"""
from __future__ import annotations

import copy
import random

from . import engineering as E
from . import hydraulics as H
from .capacity import validate_reserve
from .geometry import EPS, find_clashes
from .lattice import bends, compress, length
from .model import Index, dz_flow, evaluate_hookup, header_loads, hookup_solids, static_solids, tool_side_pressure
from .planner import own_header_exempt

SEVERITY = {"UNKNOWN_REFERENCE": "error", "WRONG_UTILITY": "error", "POC_IN_USE": "error",
            "POC_OVER_RATING": "error", "HEADER_OVER_CAPACITY": "error", "UNDERSIZED_VELOCITY": "error",
            "UNDERSIZED_PRESSURE": "error", "UNDERSIZED_RATING": "error", "MODEL_INVALID": "warning",
            "CLASH_HARD": "error", "CLASH_CLEARANCE": "warning", "ROUTE_DISCONNECTED": "error",
            "ROUTE_NOT_ORTHOGONAL": "error", "PCW_SPLIT_CORRIDOR": "error", "PCW_LOOP_UNVERIFIED": "warning"}


def _close(p, q) -> bool:
    return all(abs(p[a] - q[a]) <= 1e-6 for a in range(3))


def review(site: dict, proposal: list[dict], upgrades: dict | None = None, reserve: float = 0.0) -> list[dict]:
    validate_reserve(reserve)
    # planned hookups in the model are the proposal itself, not existing work
    site = dict(site, hookups=[h for h in site["hookups"] if h["status"] != "planned"])
    idx = Index(site)
    upgrades = upgrades or {}
    issues = []

    def add(code, hk_id, detail):
        issues.append({"code": code, "severity": SEVERITY[code], "hookup": hk_id, "detail": detail})

    existing_poc_use = {hk["poc"] for hk in site["hookups"]}
    poc_users: dict[str, list] = {}
    header_new: dict[str, float] = {}
    geom_ok = []
    supply: dict[str, tuple] = {}      # tool -> (PCWS header pressure, PCWS hookup loss)
    pcw_corridor: dict[tuple, tuple] = {}   # (tool, system) -> (corridor, hookup id)
    # PCW supplies first, so a return can be checked against its own supply's loss
    order = sorted(range(len(proposal)), key=lambda n: (proposal[n]["system"] == E.PCW_PAIR[1], n))
    for n in order:
        hk = proposal[n]
        hid = hk["id"]
        d = idx.demand.get((hk["tool"], hk["system"]))
        poc = idx.pocs.get(hk["poc"])
        if d is None or poc is None or hk["system"] not in E.SYSTEMS:
            add("UNKNOWN_REFERENCE", hid, f"tool/system/POC not in model: {hk['tool']}/{hk['system']}/{hk['poc']}")
            continue
        try:
            E.size_by_label(hk["system"], hk["size"])
        except KeyError:
            add("UNKNOWN_REFERENCE", hid, f"size {hk['size']} not in the {hk['system']} catalogue")
            continue
        if poc["system"] != hk["system"]:
            add("WRONG_UTILITY", hid, f"{hk['system']} hookup connected to {poc['system']} POC {poc['id']}")
        poc_users.setdefault(poc["id"], []).append(hid)
        if poc["id"] in existing_poc_use or poc["status"] == "in_use":
            add("POC_IN_USE", hid, f"POC {poc['id']} already serves an existing hookup")
        if d["flow"] > poc["rated_flow"] + EPS:
            add("POC_OVER_RATING", hid, f"demand {d['flow']:g} > POC rating {poc['rated_flow']:.4g} "
                                        f"{E.SYSTEMS[hk['system']]['flow_unit']}")
        if poc["system"] == hk["system"]:
            header_new[poc["header"]] = header_new.get(poc["header"], 0.0) + \
                d["flow"] * E.COINCIDENCE_FACTOR[hk["system"]]
            if hk["system"] in E.PCW_PAIR:
                pcw_corridor.setdefault((hk["tool"], hk["system"]), (idx.headers[poc["header"]]["corridor"], hid))
        pts = [tuple(p) for p in hk["points"]]
        orth = len(pts) >= 2 and all(sum(1 for a in range(3) if abs(pts[m][a] - pts[m + 1][a]) > 1e-9) <= 1
                                     for m in range(len(pts) - 1))
        if not orth:
            add("ROUTE_NOT_ORTHOGONAL", hid, "route has fewer than two points or a non axis-aligned run")
            continue
        start_ok = _close(pts[0], (poc["x"], poc["y"], poc["z"]))
        end_ok = _close(pts[-1], (d["px"], d["py"], E.FAB_FLOOR_Z))
        if not (start_ok and end_ok):
            add("ROUTE_DISCONNECTED", hid, ("start not at POC" if not start_ok else "") +
                (" / " if not start_ok and not end_ok else "") + ("end not at tool connection" if not end_ok else ""))
        geom_ok.append(hk)
        if poc["system"] != hk["system"]:
            continue
        tool_p = tool_side_pressure(hk["system"], d["p_req"], supply.get(hk["tool"]))
        if tool_p is None:
            add("PCW_LOOP_UNVERIFIED", hid, f"no checkable PCW supply hookup for {hk['tool']} in the proposal; "
                                            "return pressure not checked")
            tool_p = float("inf")
        ev = evaluate_hookup(site, hk["system"], d["flow"], tool_p, poc, pts, hk["size"])
        if E.SYSTEMS[hk["system"]]["kind"] == "power":
            if not ev["capacity_ok"]:
                add("UNDERSIZED_RATING", hid, f"breaker {hk['size']} < {E.CONTINUOUS_LOAD_FACTOR:g} x "
                                              f"{ev['design_current_a']:.4g} A ({d['flow']:g} kVA at {E.V_LL:g} V)")
            continue
        if hk["system"] == E.PCW_PAIR[0] and hk["tool"] not in supply:
            supply[hk["tool"]] = (idx.headers[poc["header"]]["pressure_kpa_g"], ev["dp_total_kpa"])
        if not ev["velocity_ok"]:
            add("UNDERSIZED_VELOCITY", hid, f"{ev['velocity']:.3g} m/s > limit {E.SYSTEMS[hk['system']]['v_max']:.3g}"
                                            f" m/s at {hk['size']}")
        if not ev["pressure_ok"]:
            loop = " (PCW loop: supply header - supply loss - tool drop - this loss < return header)" \
                if hk["system"] == E.PCW_PAIR[1] else ""
            add("UNDERSIZED_PRESSURE", hid, f"pressure loss {ev['dp_total_kpa']:.4g} kPa > available "
                                            f"{ev['available_dp_kpa']:.4g} kPa over {length(pts):.3g} m, "
                                            f"{bends(pts)} bends{loop}")
        if not ev["valid_model"]:
            add("MODEL_INVALID", hid, "gas pressure drop >= 10 % of inlet absolute pressure; "
                                      "incompressible Darcy-Weisbach not valid")
    for tool in sorted({t for t, _ in pcw_corridor}):
        s, r = pcw_corridor.get((tool, E.PCW_PAIR[0])), pcw_corridor.get((tool, E.PCW_PAIR[1]))
        if s and r and s[0] != r[0]:
            for hid in (s[1], r[1]):
                add("PCW_SPLIT_CORRIDOR", hid, f"{tool}: PCW supply on corridor {s[0]}, return on corridor {r[0]}")
    for pid, users in sorted(poc_users.items()):
        if len(users) > 1:
            for u in users:
                add("POC_IN_USE", u, f"POC {pid} used by {len(users)} proposed hookups: {', '.join(users)}")
    loads = header_loads(site)
    for h, new in sorted(header_new.items()):
        hdr = idx.headers[h]
        cap = hdr["capacity"] * (1.0 - reserve) + upgrades.get(h, 0) * hdr["upgrade_step"]
        if loads[h] + new > cap + EPS:
            users = [hk["id"] for hk in proposal if hk["poc"] in idx.pocs and idx.pocs[hk["poc"]]["header"] == h]
            for u in users:
                add("HEADER_OVER_CAPACITY", u, f"header {h}: existing {loads[h]:g} + proposed {new:g} > usable "
                                               f"{cap:g} {E.SYSTEMS[hdr['system']]['flow_unit']}")
    existing = static_solids(site) + [s for hk in site["hookups"] for s in hookup_solids(hk)]
    solids = [s for hk in geom_ok for s in hookup_solids(hk)]
    for c in find_clashes(solids, existing, E.CLEARANCE_M, own_header_exempt(site)):
        a = c["a"].split("#")[0]
        code = "CLASH_HARD" if c["type"] == "hard" else "CLASH_CLEARANCE"
        add(code, a, f"{c['a']} vs {c['b_kind']} {c['b']}: gap {c['gap_m']:.3f} m")
    issues.sort(key=lambda i: (i["hookup"], i["code"], i["detail"]))
    return issues


# --- fault injection ------------------------------------------------------------------------
# Check-coverage test: each fault is constructed to violate one rule, and the test records
# whether that rule fires.  This is circular by design (the faults were written for the
# checks), so it only shows that each check is wired up.
RULE_FAULTS = {
    "wrong_utility": {"WRONG_UTILITY"},
    "undersized_line": {"UNDERSIZED_VELOCITY", "UNDERSIZED_PRESSURE", "UNDERSIZED_RATING", "MODEL_INVALID"},
    "clash": {"CLASH_HARD"},
    "poc_over_rating": {"POC_OVER_RATING"},
    "header_over_capacity": {"HEADER_OVER_CAPACITY"},
    "duplicate_poc": {"POC_IN_USE"},
    "disconnected_route": {"ROUTE_DISCONNECTED"},
    "pcw_split_corridor": {"PCW_SPLIT_CORRIDOR"},
}
# Faults written after the checks, without a rule aimed at them.  A case counts as caught if
# any finding at all lands on a faulted hookup; which checks fired is reported.
OPEN_FAULTS = ["unit_lpm_read_as_m3h", "unit_m3h_read_as_lpm", "gas_dp_over_10pct", "supply_return_swapped",
               "route_to_wrong_tool"]
FAULTS = dict(RULE_FAULTS)   # kept for the sample report in pipeline.demo_proposal


def _redirect_end(points: list, px: float, py: float) -> list:
    """Re-draw the last riser of a route so it ends at (px, py) on the fab floor instead."""
    q = points[-2]
    pts = [tuple(p) for p in points[:-1]] + [(px, q[1], q[2]), (px, py, q[2]), (px, py, E.FAB_FLOOR_Z)]
    dedup = [pts[0]]
    for p in pts[1:]:
        if not _close(p, dedup[-1]):
            dedup.append(p)
    return [list(p) for p in compress(dedup)]


def _drafter_size(site: dict, hk: dict, flow: float) -> str:
    """Size a drafter would pick by velocity for ``flow`` (largest size if none is fast enough)."""
    idx = Index(site)
    hp = idx.headers[idx.pocs[hk["poc"]]["header"]]["pressure_kpa_g"]
    s = H.min_size_velocity(hk["system"], flow, hp)
    return (s or E.sizes_for(hk["system"])[-1])["label"]


def inject(site: dict, proposal: list[dict], upgrades: dict, fault: str, target: int, rng: random.Random):
    """Return (proposal, upgrades, injected hookup ids) with one fault, or None if not applicable."""
    idx = Index(site)
    prop = copy.deepcopy(proposal)
    ups = dict(upgrades)
    hk = prop[target]
    used = {h["poc"] for h in site["hookups"]} | {h["poc"] for h in prop}
    free = [p for p in site["pocs"] if p["id"] not in used and p["status"] == "free"]
    partner = None
    if hk["system"] in E.PCW_PAIR:
        other = E.PCW_PAIR[1] if hk["system"] == E.PCW_PAIR[0] else E.PCW_PAIR[0]
        partner = next((h for h in prop if h["tool"] == hk["tool"] and h["system"] == other), None)
    unit = E.SYSTEMS[hk["system"]]["flow_unit"]
    d = idx.demand.get((hk["tool"], hk["system"]))
    if fault == "wrong_utility":
        opts = [p for p in free if p["system"] != hk["system"]]
        if not opts:
            return None
        hk["poc"] = opts[rng.randrange(len(opts))]["id"]
    elif fault == "undersized_line":
        sizes = E.sizes_for(hk["system"])
        n = E.size_index(hk["system"], hk["size"])
        if n == 0:
            return None
        hk["size"] = sizes[n - 1]["label"]
    elif fault == "clash":
        col = min(site["columns"], key=lambda c: (abs(c["x"] - hk["points"][0][0]) + abs(c["y"] - hk["points"][0][1]),
                                                  c["id"]))
        p0, pe = hk["points"][0], hk["points"][-1]
        zr = (site["meta"]["kmax"]) * site["meta"]["step"]
        pts = [p0, [p0[0], p0[1], zr], [col["x"], p0[1], zr], [col["x"], col["y"], zr], [pe[0], col["y"], zr],
               [pe[0], pe[1], zr], pe]
        hk["points"] = [p for n, p in enumerate(pts) if n == 0 or p != pts[n - 1]]
    elif fault == "poc_over_rating":
        opts = [p for p in free if p["system"] == hk["system"] and p["rated_flow"] < d["flow"]]
        if partner is not None:   # keep a PCW pair on one corridor so only the rating rule is violated
            want = idx.headers[idx.pocs[partner["poc"]]["header"]]["corridor"]
            opts = [p for p in opts if idx.headers[p["header"]]["corridor"] == want]
        if not opts:
            return None
        hk["poc"] = opts[rng.randrange(len(opts))]["id"]
    elif fault == "header_over_capacity":
        hdr = idx.pocs[hk["poc"]]["header"]
        if ups.get(hdr, 0) == 0:
            return None
        ups[hdr] -= 1
        ids = [h["id"] for h in prop if idx.pocs.get(h["poc"], {}).get("header") == hdr]
        return prop, ups, ids
    elif fault == "duplicate_poc":
        others = [h for n, h in enumerate(prop) if n != target and h["system"] == hk["system"]]
        if not others:
            return None
        other = others[rng.randrange(len(others))]
        hk["poc"] = other["poc"]
        return prop, ups, [hk["id"], other["id"]]
    elif fault == "disconnected_route":
        hk["points"] = hk["points"][:-1] if len(hk["points"]) > 2 else hk["points"]
        last = hk["points"][-1]
        if _close(tuple(last), tuple(proposal[target]["points"][-1])):
            return None
    elif fault == "pcw_split_corridor":
        if hk["system"] != E.PCW_PAIR[1] or partner is None:
            return None
        here = idx.headers[idx.pocs[partner["poc"]]["header"]]["corridor"]
        opts = [p for p in free if p["system"] == hk["system"] and p["rated_flow"] >= d["flow"]
                and idx.headers[p["header"]]["corridor"] != here]
        if not opts:
            return None
        hk["poc"] = opts[rng.randrange(len(opts))]["id"]
        return prop, ups, [hk["id"], partner["id"]]
    elif fault in ("unit_lpm_read_as_m3h", "unit_m3h_read_as_lpm"):
        # the drafter sized the line from the demand read in the wrong unit
        if fault == "unit_lpm_read_as_m3h":
            if unit != "L/min":
                return None
            wrong = d["flow"] * 1000.0 / 60.0      # X L/min taken as X m3/h, expressed in L/min
        else:
            if unit not in ("m3/h", "Sm3/h"):
                return None
            wrong = d["flow"] * 60.0 / 1000.0      # X m3/h taken as X L/min, expressed in m3/h
        new = _drafter_size(site, hk, wrong)
        if new == hk["size"]:
            return None
        hk["size"] = new
    elif fault == "gas_dp_over_10pct":
        if E.SYSTEMS[hk["system"]]["kind"] != "gas":
            return None
        hp = idx.headers[idx.pocs[hk["poc"]]["header"]]["pressure_kpa_g"]
        pts = [tuple(p) for p in hk["points"]]
        limit = E.GAS_DP_FRACTION_MAX * H.abs_pressure_kpa(hp)
        sizes = E.sizes_for(hk["system"])
        smaller = [s for s in sizes[:E.size_index(hk["system"], hk["size"])]
                   if H.line_loss(hk["system"], d["flow"], s["id"], length(pts), bends(pts),
                                  dz_flow(hk["system"], idx.pocs[hk["poc"]]["z"]), hp)["dp_total_kpa"] >= limit]
        if not smaller:
            return None
        hk["size"] = smaller[-1]["label"]          # the largest size whose loss breaks the 10 % limit
    elif fault == "supply_return_swapped":
        if hk["system"] != E.PCW_PAIR[0] or partner is None:
            return None
        ds, dr = d, idx.demand[(partner["tool"], partner["system"])]
        hk["points"] = _redirect_end(hk["points"], dr["px"], dr["py"])
        partner["points"] = _redirect_end(partner["points"], ds["px"], ds["py"])
        return prop, ups, [hk["id"], partner["id"]]
    elif fault == "route_to_wrong_tool":
        others = sorted((dd for (t, s), dd in idx.demand.items() if s == hk["system"] and t != hk["tool"]
                         and idx.tools[t]["status"] == "new"), key=lambda dd: dd["tool"])
        if not others:
            return None
        o = others[rng.randrange(len(others))]
        hk["points"] = _redirect_end(hk["points"], o["px"], o["py"])
    else:
        raise KeyError(fault)
    return prop, ups, [hk["id"]]


def _touched_headers(site, before, after, ids) -> set:
    """Headers whose load changes when the injected hookups move to other POCs."""
    pocs = Index(site).pocs
    out = set()
    for prop in (before, after):
        for h in prop:
            if h["id"] in ids and h["poc"] in pocs:
                out.add(pocs[h["poc"]]["header"])
    return out


def _pcw_partners(proposal, ids) -> set:
    tools = {h["tool"] for h in proposal if h["id"] in ids and h["system"] in E.PCW_PAIR}
    return {h["id"] for h in proposal if h["tool"] in tools and h["system"] in E.PCW_PAIR and h["id"] not in ids}


def _classify(site, proposal, prop, ids, iss) -> tuple[list, list, list]:
    """Split findings into: on the faulted hookups / explained elsewhere / unexplained elsewhere.

    A finding on an untouched hookup is *explained* when it follows mechanically from the
    fault: a clash with a faulted run, the load of a header the fault changed, or the
    pressure/pairing check of the PCW partner of a faulted hookup.
    """
    touched = _touched_headers(site, proposal, prop, ids)
    partners = _pcw_partners(proposal, ids)
    on_target = [i for i in iss if i["hookup"] in ids]
    explained, unexplained = [], []
    for i in iss:
        if i["hookup"] in ids:
            continue
        if (i["code"] in ("CLASH_HARD", "CLASH_CLEARANCE") and any(x in i["detail"] for x in ids)) \
                or (i["code"] == "HEADER_OVER_CAPACITY" and i["detail"].split(":")[0][len("header "):] in touched) \
                or (i["hookup"] in partners and i["code"] in ("UNDERSIZED_PRESSURE", "PCW_SPLIT_CORRIDOR",
                                                              "PCW_LOOP_UNVERIFIED")):
            explained.append(i)
        else:
            unexplained.append(i)
    return on_target, explained, unexplained


def _count(codes) -> dict:
    out: dict = {}
    for c in codes:
        out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items()))


def evaluate_faults(site: dict, proposal: list[dict], upgrades: dict, per_fault: int = 8, seed: int = 7) -> dict:
    """Inject one fault at a time into a clean proposal and record what the review reports."""
    rng = random.Random(seed)
    base = review(site, proposal, upgrades)
    out = {"clean_issues": len(base), "rule_faults": {}, "open_faults": {}}
    for fault in list(RULE_FAULTS) + OPEN_FAULTS:
        order = list(range(len(proposal)))
        rng.shuffle(order)
        cases, not_applicable = [], 0
        for t in order:
            if len(cases) >= per_fault:
                break
            inj = inject(site, proposal, upgrades, fault, t, rng)
            if inj is None:
                not_applicable += 1
                continue
            prop, ups, ids = inj
            iss = review(site, prop, ups)
            on_target, explained, unexplained = _classify(site, proposal, prop, ids, iss)
            codes = {i["code"] for i in on_target}
            case = {"target": proposal[t]["id"], "faulted": ids, "codes_on_target": sorted(codes),
                    "caught": bool(codes), "explained_elsewhere": len(explained),
                    "unexplained_elsewhere": len(unexplained),
                    "unexplained_codes": sorted({i["code"] for i in unexplained})}
            if fault in RULE_FAULTS:
                case["expected_fired"] = bool(codes & RULE_FAULTS[fault])
            cases.append(case)
        res = {"injected": len(cases), "not_applicable_targets": not_applicable,
               "caught": sum(c["caught"] for c in cases),
               "codes_on_target": _count(c for case in cases for c in case["codes_on_target"]),
               "explained_elsewhere": sum(c["explained_elsewhere"] for c in cases),
               "unexplained_elsewhere": sum(c["unexplained_elsewhere"] for c in cases), "cases": cases}
        if fault in RULE_FAULTS:
            res["expected_codes"] = sorted(RULE_FAULTS[fault])
            res["expected_fired"] = sum(c["expected_fired"] for c in cases)
            out["rule_faults"][fault] = res
        else:
            out["open_faults"][fault] = res
    return out


def report_md(issues: list[dict], title: str) -> str:
    lines = [f"# {title}", "", "Illustrative synthetic data. Automated checks only; not a substitute for "
             "engineering review.", ""]
    if not issues:
        lines += ["No issues found.", ""]
        return "\n".join(lines)
    counts: dict = {}
    for i in issues:
        counts[i["code"]] = counts.get(i["code"], 0) + 1
    lines += ["| Check | Severity | Findings |", "|---|---|---|"]
    lines += [f"| {c} | {SEVERITY[c]} | {n} |" for c, n in sorted(counts.items())]
    lines += ["", "| Hookup | Check | Detail |", "|---|---|---|"]
    lines += [f"| {i['hookup']} | {i['code']} | {i['detail']} |" for i in issues]
    return "\n".join(lines) + "\n"
