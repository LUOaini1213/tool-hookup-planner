"""Header capacity check for a set of new tools.

load_new  = sum(peak demand x coincidence factor) of the new tools (coincidence factor 1.0
            unless a cited value exists -- see engineering.COINCIDENCE_FACTOR)
usable    = design capacity x (1 - reserve)          reserve is a planning parameter (default 0)
remaining = usable - connected load of existing hookups
shortfall = max(0, load_new - remaining)  ->  header capacity steps (process lateral work), illustrative cost
The system-level step count is a lower bound; the assignment (assign.py) decides on which
header the steps are actually needed.
"""
from __future__ import annotations

import math

from . import engineering as E
from .model import Index, header_loads


def new_demand(site: dict, tools: list[str] | None = None) -> list[dict]:
    idx = Index(site)
    sel = set(tools) if tools is not None else {t["id"] for t in site["tools"] if t["status"] == "new"}
    out = [d for d in site["demands"] if d["tool"] in sel and idx.tools[d["tool"]]["status"] == "new"]
    return sorted(out, key=lambda d: (d["tool"], E.SYSTEM_ORDER.index(d["system"])))


def capacity_check(site: dict, tools: list[str] | None = None, reserve: float = 0.0) -> dict:
    if not 0.0 <= reserve < 1.0:
        raise ValueError("reserve must be in [0, 1)")
    loads = header_loads(site)
    reqs = new_demand(site, tools)
    headers = []
    for h in sorted(site["headers"], key=lambda h: h["id"]):
        usable = h["capacity"] * (1.0 - reserve)
        headers.append({"header": h["id"], "system": h["system"], "capacity": h["capacity"], "usable": usable,
                        "connected_load": loads[h["id"]], "remaining": usable - loads[h["id"]],
                        "free_pocs": sum(1 for p in site["pocs"] if p["header"] == h["id"] and p["status"] == "free")})
    systems = []
    for s in E.SYSTEM_ORDER:
        hs = [h for h in headers if h["system"] == s]
        if not hs:
            continue
        step = min(x["upgrade_step"] for x in site["headers"] if x["system"] == s)
        cost = min(x["upgrade_cost"] for x in site["headers"] if x["system"] == s)
        new = sum(d["flow"] * E.COINCIDENCE_FACTOR[s] for d in reqs if d["system"] == s)
        n_new = sum(1 for d in reqs if d["system"] == s)
        remaining = sum(h["remaining"] for h in hs)
        usable = sum(h["usable"] for h in hs)
        shortfall = max(0.0, new - remaining)
        steps = math.ceil(shortfall / step - 1e-9) if shortfall > 0 else 0
        systems.append({
            "system": s, "unit": E.SYSTEMS[s]["flow_unit"], "coincidence_factor": E.COINCIDENCE_FACTOR[s],
            "usable": usable, "connected_load": sum(h["connected_load"] for h in hs),
            "remaining": remaining, "new_load": new, "new_connections": n_new,
            "free_pocs": sum(h["free_pocs"] for h in hs),
            "margin": remaining - new,
            "utilisation_after": (usable - remaining + new) / usable if usable > 0 else None,
            "status": "SHORTFALL" if shortfall > 0 else "OK",
            "min_upgrade_steps": steps, "min_upgrade_cost": steps * cost,
            "poc_shortfall": max(0, n_new - sum(h["free_pocs"] for h in hs))})
    return {"reserve": reserve, "systems": systems, "headers": headers,
            "total_min_upgrade_cost": sum(s["min_upgrade_cost"] for s in systems)}
