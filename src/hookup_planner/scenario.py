"""Synthetic sub-fab generator (ILLUSTRATIVE data only).

Builds a deterministic site from data/scenario.json: structural grid and columns, utility
headers in corridors, POCs, sub-fab support equipment, existing tools with as-built
hookups (assigned to the nearest feasible POC and routed with the same A* router), and
new tools whose hookups are to be planned.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from . import engineering as E
from . import hydraulics as H
from .model import Index, build_lattice, header_loads, hookup_solids, route_one, tool_side_pressure
from .numfmt import r10

NOTICE = ("ILLUSTRATIVE SYNTHETIC DATA - invented sub-fab, utilities and tools; "
          "not any real facility, company or equipment.")

# corridor layouts: (system, j offset from corridor centre line, k level, outer diameter m)
WET = [("PCWS", -1, 3, 0.16828), ("PCWR", 1, 3, 0.16828), ("UPW", 0, 5, 0.1143),
       ("CDA", -1, 6, 0.0889), ("N2", 1, 6, 0.0889)]
EXH = [("AEX", -2, 4, 0.6), ("SEX", 2, 4, 0.5), ("GEX", 0, 6, 0.7), ("PWR", -4, 7, 0.2)]
PEN_PATTERN = [(0, 0), (2, 0), (0, 2), (2, 2), (0, 4), (2, 4), (0, 6), (2, 6)]


def load_config(path=None) -> dict:
    path = Path(path) if path else Path(__file__).resolve().parents[2] / "data" / "scenario.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_rates(path=None) -> dict:
    path = Path(path) if path else Path(__file__).resolve().parents[2] / "data" / "unit_rates.json"
    return json.loads(path.read_text(encoding="utf-8"))


def rated_flow(system: str, size_label: str, header_p: float) -> float:
    """POC rating = flow at the system velocity limit through the POC size (or kVA rating)."""
    s = E.size_by_label(system, size_label)
    if E.SYSTEMS[system]["kind"] == "power":
        return E.breaker_kva(s["amps"])
    q_act = E.SYSTEMS[system]["v_max"] * E.area(s["id"])        # m3/s actual
    kind = E.SYSTEMS[system]["kind"]
    if kind == "liquid":
        return q_act * 60000.0
    if kind == "gas":
        return q_act * 3600.0 * (H.abs_pressure_kpa(header_p) / E.P_ATM_KPA) * (E.T_STD_K / E.T_OP_K)
    return q_act * 3600.0


def systems_table() -> list[dict]:
    return [{"code": c, "name": E.SYSTEMS[c]["name"], "kind": E.SYSTEMS[c]["kind"],
             "role": E.SYSTEMS[c]["role"], "fluid": E.SYSTEMS[c]["fluid"] or "",
             "flow_unit": E.SYSTEMS[c]["flow_unit"], "material": E.SYSTEMS[c]["material"],
             "v_max": r10(E.SYSTEMS[c]["v_max"]) if E.SYSTEMS[c]["v_max"] else 0.0,
             "coincidence_factor": E.COINCIDENCE_FACTOR[c]} for c in E.SYSTEM_ORDER]


def generate(cfg: dict | None = None, rates: dict | None = None) -> dict:
    cfg = cfg or load_config()
    rates = rates or load_rates()
    rng = random.Random(cfg["seed"])
    step, bn = cfg["step_m"], cfg["bay_nodes"]
    nx, ny = cfg["bays_x"] * bn + 1, cfg["bays_y"] * bn + 1
    nz = cfg["kmax"] + 2
    meta = {"name": cfg["name"], "seed": cfg["seed"], "notice": NOTICE, "step": step,
            "nx": nx, "ny": ny, "nz": nz, "kmin": cfg["kmin"], "kmax": cfg["kmax"], "bay_nodes": bn,
            "subfab_height": r10((nz - 1) * step), "fab_floor_z": E.FAB_FLOOR_Z}
    site = {"meta": meta, "systems": systems_table(), "columns": [], "headers": [], "pocs": [],
            "equipment": [], "tools": [], "demands": [], "hookups": []}

    # structural grid: columns at every bay corner
    for bi in range(cfg["bays_x"] + 1):
        for bj in range(cfg["bays_y"] + 1):
            site["columns"].append({"id": f"C-{bi:02d}-{bj:02d}", "x": r10(bi * bn * step),
                                    "y": r10(bj * bn * step), "w": 0.5, "d": 0.5,
                                    "z0": 0.0, "z1": meta["subfab_height"]})

    # headers by corridor (mid-bay in every bay row)
    hp = cfg["header_pressure_kpa_g"]
    for row in range(cfg["bays_y"]):
        letter = chr(ord("A") + row)
        jc = row * bn + bn // 2
        layout = WET if row % 2 == 0 else EXH
        for sysc, dj, k, od in layout:
            hid = f"{sysc}-{letter}"
            site["headers"].append({
                "id": hid, "system": sysc, "corridor": letter, "y": r10((jc + dj) * step), "z": r10(k * step),
                "x0": r10(2 * step), "x1": r10((nx - 3) * step), "od": od, "capacity": 0.0,
                "pressure_kpa_g": float(hp[sysc]),
                "upgrade_step": float(rates["header_upgrade"][sysc]["step"]),
                "upgrade_cost": float(rates["header_upgrade"][sysc]["cost"]),
                "upgrade_days": float(rates["header_upgrade"][sysc]["days"])})
            sizes = cfg["poc_sizes"][sysc]
            for m, i in enumerate(range(3, nx - 3, 6)):
                lab = sizes[(m + row) % len(sizes)]
                site["pocs"].append({"id": f"{hid}-P{m + 1:02d}", "header": hid, "system": sysc,
                                     "x": r10(i * step), "y": r10((jc + dj) * step), "z": r10(k * step),
                                     "size": lab, "rated_flow": r10(rated_flow(sysc, lab, hp[sysc])),
                                     "status": "free"})

    # tool slots: two per bay
    slots = []
    for by in range(cfg["bays_y"]):
        for bx in range(cfg["bays_x"]):
            for s in (0, 1):
                x0 = bx * bn * step + (0.9 if s == 0 else 3.9)
                y0 = by * bn * step + 1.5
                slots.append((r10(x0), r10(y0), r10(x0 + 2.4), r10(y0 + 4.2)))
    rng.shuffle(slots)
    n_ex, n_new = cfg["n_existing_tools"], cfg["n_new_tools"]
    cats = sorted(cfg["tool_categories"])
    for t in range(n_ex + n_new):
        x0, y0, x1, y1 = slots[t]
        status = "existing" if t < n_ex else "new"
        tid = f"T-{'X' if status == 'existing' else 'N'}{(t if t < n_ex else t - n_ex) + 1:02d}"
        cat = cats[rng.randrange(len(cats))]
        site["tools"].append({"id": tid, "category": cat, "status": status,
                              "x0": x0, "y0": y0, "x1": x1, "y1": y1, "height": 2.5})
        i0, j0 = math.ceil(x0 / step - 1e-9), math.ceil(y0 / step - 1e-9)
        pcw_flow = None
        for n, sysc in enumerate(s for s in E.SYSTEM_ORDER if s in cfg["tool_categories"][cat]["systems"]):
            di, dj = PEN_PATTERN[n]
            if sysc == "PCWR":
                flow = pcw_flow
            else:
                lo, hi = cfg["demand_range"][sysc]
                flow = float(rng.randint(lo, hi))
                if sysc == "PCWS":
                    pcw_flow = flow
            if sysc == E.PCW_PAIR[1]:
                # PCW return: p_req holds the tool's internal pressure drop (kPa), not a gauge pressure
                lo, hi = cfg["pcw_tool_dp_range_kpa"]
                p_req = float(rng.randint(lo // 5, hi // 5) * 5)
            elif sysc in cfg["pressure_req_range_kpa_g"]:
                lo, hi = cfg["pressure_req_range_kpa_g"][sysc]
                if E.SYSTEMS[sysc]["kind"] == "exhaust":
                    p_req = r10(rng.randint(round(lo * 20), round(hi * 20)) / 20.0)
                else:
                    p_req = float(rng.randint(lo // 5, hi // 5) * 5)
            else:
                p_req = 0.0
            site["demands"].append({"tool": tid, "system": sysc, "flow": flow, "p_req": p_req,
                                    "px": r10((i0 + di) * step), "py": r10((j0 + dj) * step)})
        if rng.random() < cfg["equipment_probability"]:
            cx, cy = (i0 + 1) * step, (j0 + 3) * step
            site["equipment"].append({"id": f"EQ-{tid}", "x0": r10(cx - 0.45), "y0": r10(cy - 0.6), "z0": 0.0,
                                      "x1": r10(cx + 0.45), "y1": r10(cy + 0.6), "z1": 1.2})

    _build_existing_hookups(site)
    _set_capacities(site, cfg, rng)
    return site


def _build_existing_hookups(site: dict) -> None:
    """As-built hookups of existing tools: nearest feasible free POC, routed with A*."""
    idx = Index(site)
    lat = build_lattice(site, include_hookups=False)
    reqs = [d for d in site["demands"] if idx.tools[d["tool"]]["status"] == "existing"]
    reqs.sort(key=lambda d: (E.SYSTEM_ORDER.index(d["system"]), d["tool"]))
    supply: dict[str, tuple] = {}      # tool -> (PCWS header pressure, PCWS hookup loss, corridor)
    for d in reqs:
        cands = []
        for p in site["pocs"]:
            if p["system"] != d["system"] or p["status"] != "free" or p["rated_flow"] < d["flow"]:
                continue
            if d["system"] == E.PCW_PAIR[1] and idx.headers[p["header"]]["corridor"] != supply[d["tool"]][2]:
                continue   # PCW return on the same corridor as the tool's supply
            dist = abs(p["x"] - d["px"]) + abs(p["y"] - d["py"]) + abs(E.FAB_FLOOR_Z - p["z"])
            cands.append((round(dist, 6), p["id"]))
        tool_p = tool_side_pressure(d["system"], d["p_req"], supply.get(d["tool"]))
        for _, pid in sorted(cands):
            poc = idx.pocs[pid]
            res = route_one(site, lat, d["system"], d["flow"], tool_p, poc, (d["px"], d["py"]))
            if "error" in res:
                continue
            if d["system"] == E.PCW_PAIR[0]:
                hdr = idx.headers[poc["header"]]
                supply[d["tool"]] = (hdr["pressure_kpa_g"], res["eval"]["dp_total_kpa"], hdr["corridor"])
            hk = {"id": f"HX-{d['tool'][2:]}-{d['system']}", "tool": d["tool"], "system": d["system"],
                  "poc": pid, "status": "released", "size": res["size"],
                  "points": [[r10(v) for v in p] for p in res["points"]]}
            site["hookups"].append(hk)
            poc["status"] = "in_use"
            lat.add_route(hookup_solids(hk))
            break
        else:
            raise RuntimeError(f"generator could not hook up existing {d['tool']} {d['system']}")


def _set_capacities(site: dict, cfg: dict, rng: random.Random) -> None:
    """Header design capacity = existing load + headroom (relative to the new-tool demand)."""
    idx = Index(site)
    loads = header_loads(site)
    new_dem = {s: 0.0 for s in E.SYSTEM_ORDER}
    for d in site["demands"]:
        if idx.tools[d["tool"]]["status"] == "new":
            new_dem[d["system"]] += d["flow"]
    n_hdr = {s: sum(1 for h in site["headers"] if h["system"] == s) for s in E.SYSTEM_ORDER}
    for h in site["headers"]:
        s = h["system"]
        q = cfg["capacity_quantum"][s]
        head = cfg["headroom_factor"][s] * new_dem[s] / n_hdr[s] * rng.uniform(0.8, 1.2)
        h["capacity"] = float(math.ceil((loads[h["id"]] + head) / q) * q)
