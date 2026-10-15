"""Material take-off and cost estimate with explicit ILLUSTRATIVE unit rates (data/unit_rates.json).

Process-lateral (PLS) items are the header capacity steps and new POCs the plan relies on;
hookups run from a POC to the tool.
"""
from __future__ import annotations

from . import engineering as E

CATEGORY = {"liquid": "pipe", "gas": "pipe", "exhaust": "duct", "power": "cable"}


def material_rate(rates: dict, system: str, size_label: str) -> float:
    s = E.size_by_label(system, size_label)
    mat = E.SYSTEMS[system]["material"]
    r = rates["material_per_m"][mat]
    if E.SYSTEMS[system]["kind"] == "power":
        return r["a"] + r["per_amp"] * s["amps"]
    return r["a"] + r["b"] * s["od"] * 1000.0


def elbow_rate(rates: dict, system: str, size_label: str) -> float:
    s = E.size_by_label(system, size_label)
    return rates["elbow_each"]["a"] + rates["elbow_each"]["b"] * s["od"] * 1000.0


def hookup_cost(rates: dict, hk: dict) -> dict:
    kind = E.SYSTEMS[hk["system"]]["kind"]
    L = hk["length_m"]
    elbows = hk["bends"] if kind != "power" else 0
    material = L * material_rate(rates, hk["system"], hk["size"])
    fittings = elbows * elbow_rate(rates, hk["system"], hk["size"]) if elbows else 0.0
    labour_h = L * rates["labour_h_per_m"][kind]
    labour = labour_h * rates["labour_rate_per_h"]
    tie_in = rates["poc_tie_in_each"][kind]
    test = rates["test_each"][kind]
    return {"hookup": hk["id"], "tool": hk["tool"], "system": hk["system"], "material": material,
            "fittings": fittings, "labour_h": labour_h, "labour": labour, "tie_in": tie_in, "test": test,
            "total": material + fittings + labour + tie_in + test}


def take_off(hookups: list[dict]) -> list[dict]:
    rows: dict = {}
    for hk in hookups:
        kind = E.SYSTEMS[hk["system"]]["kind"]
        key = (CATEGORY[kind], hk["system"], E.SYSTEMS[hk["system"]]["material"], hk["size"])
        row = rows.setdefault(key, {"category": key[0], "system": key[1], "material": key[2], "size": key[3],
                                    "length_m": 0.0, "elbows": 0, "hookups": 0})
        row["length_m"] += hk["length_m"]
        row["elbows"] += hk["bends"] if kind != "power" else 0
        row["hookups"] += 1
    return [rows[k] for k in sorted(rows, key=lambda k: (k[0], E.SYSTEM_ORDER.index(k[1]),
                                                        E.size_index(k[1], k[3])))]


def estimate(rates: dict, hookups: list[dict], upgrades: dict, site: dict) -> dict:
    per = [hookup_cost(rates, hk) for hk in hookups]
    hdr = {h["id"]: h for h in site["headers"]}
    pls = [{"item": f"Header capacity step {h} x{n}", "header": h, "steps": n, "cost": hdr[h]["upgrade_cost"] * n}
           for h, n in sorted(upgrades.items())]
    new_pocs = sorted({hk["poc"] for hk in hookups if hk.get("new_poc")})
    pls += [{"item": f"New POC {p}", "header": p.rsplit("-", 1)[0], "steps": 1, "cost": rates["new_poc_each"]}
            for p in new_pocs]
    by_system = {}
    for c in per:
        by_system[c["system"]] = by_system.get(c["system"], 0.0) + c["total"]
    cats = {k: sum(c[k] for c in per) for k in ("material", "fittings", "labour", "tie_in", "test")}
    hook_total = sum(c["total"] for c in per)
    pls_total = sum(b["cost"] for b in pls)
    return {"currency": rates["currency"], "per_hookup": per, "pls_items": pls,
            "by_system": {s: by_system[s] for s in E.SYSTEM_ORDER if s in by_system},
            "by_category": cats, "hookup_total": hook_total, "pls_total": pls_total,
            "grand_total": hook_total + pls_total, "labour_h": sum(c["labour_h"] for c in per)}
