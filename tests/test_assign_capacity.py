import itertools
import math

import pytest

from hookup_planner import assign as A
from hookup_planner.capacity import capacity_check
from hookup_planner.model import header_loads

RATES = {"assignment_cost_per_m": {"PCWS": 260.0, "CDA": 210.0}, "new_poc_each": 6000.0}


def tiny_site(cap1=100.0, cap2=70.0):
    hdr = lambda i, cap, cost: {"id": i, "system": "PCWS", "corridor": "A", "y": 3.0, "z": 1.8, "x0": 1.2,
                                "x1": 30.0, "od": 0.17, "capacity": cap, "pressure_kpa_g": 520.0,
                                "upgrade_step": 40.0, "upgrade_cost": cost, "upgrade_days": 5.0}
    poc = lambda i, h, rated=300.0, status="free": {"id": i, "header": h, "system": "PCWS", "x": 3.0, "y": 3.0,
                                                     "z": 1.8, "size": "NPS 1", "rated_flow": rated, "status": status}
    return {"meta": {}, "columns": [], "equipment": [], "systems": [],
            "headers": [hdr("H1", cap1, 5000.0), hdr("H2", cap2, 7000.0)],
            "pocs": [poc("P1", "H1"), poc("P2", "H1"), poc("P3", "H2"), poc("P4", "H2"), poc("P9", "H1", 300, "in_use")],
            "tools": [{"id": "T-X01", "status": "existing"}, {"id": "T-N01", "status": "new"},
                      {"id": "T-N02", "status": "new"}, {"id": "T-N03", "status": "new"}],
            "demands": [{"tool": "T-X01", "system": "PCWS", "flow": 55.0, "p_req": 400.0, "px": 0, "py": 0},
                        {"tool": "T-N01", "system": "PCWS", "flow": 47.0, "p_req": 400.0, "px": 0, "py": 0},
                        {"tool": "T-N02", "system": "PCWS", "flow": 38.0, "p_req": 400.0, "px": 0, "py": 0},
                        {"tool": "T-N03", "system": "PCWS", "flow": 29.0, "p_req": 400.0, "px": 0, "py": 0}],
            "hookups": [{"id": "HX-X01-PCWS", "tool": "T-X01", "system": "PCWS", "poc": "P9", "status": "released",
                         "size": "NPS 1", "points": []}]}


REQS = [{"tool": "T-N01", "system": "PCWS", "flow": 47.0}, {"tool": "T-N02", "system": "PCWS", "flow": 38.0},
        {"tool": "T-N03", "system": "PCWS", "flow": 29.0}]
CAND = {0: {"P1": 12.0, "P3": 5.4, "H2-N012@0": 3.0}, 1: {"P1": 6.6, "P2": 9.0, "P4": 4.2},
        2: {"P2": 7.8, "P3": 3.6, "P4": 11.4}}
NEW = {"H2-N012@0": {"id": "H2-N012", "header": "H2", "system": "PCWS"}}


def brute_force(site, reqs, cand, capacity=True):
    hdr = {h["id"]: h for h in site["headers"]}
    pocs = {p["id"]: p["header"] for p in site["pocs"]}
    rem = {h: hdr[h]["capacity"] - header_loads(site)[h] for h in hdr}
    best = math.inf
    for choice in itertools.product(*[list(cand[r]) for r in range(len(reqs))]):
        pos = [c.split("@")[0] for c in choice]
        if len(set(pos)) < len(pos):
            continue
        cost = sum(RATES["assignment_cost_per_m"]["PCWS"] * cand[r][c] + (6000.0 if "@" in c else 0.0)
                   for r, c in enumerate(choice))
        if capacity:
            load = {h: 0.0 for h in hdr}
            for r, c in enumerate(choice):
                load[NEW[c]["header"] if "@" in c else pocs[c]] += reqs[r]["flow"]
            for h in hdr:
                if load[h] > rem[h]:
                    cost += math.ceil((load[h] - rem[h]) / hdr[h]["upgrade_step"]) * hdr[h]["upgrade_cost"]
        best = min(best, cost)
    return best


@pytest.mark.parametrize("cap1,cap2", [(100.0, 70.0), (160.0, 30.0), (58.0, 300.0), (400.0, 400.0)])
def test_milp_matches_brute_force(cap1, cap2):
    site = tiny_site(cap1, cap2)
    res = A.solve(site, REQS, CAND, NEW, RATES)
    assert res["unassigned"] == []
    assert res["objective"] == pytest.approx(brute_force(site, REQS, CAND), abs=1e-6)


def test_capacity_free_milp_equals_hungarian_and_brute_force():
    site = tiny_site(10.0, 10.0)
    m = A.solve(site, REQS, CAND, NEW, RATES, capacity=False)
    h = A.hungarian(site, REQS, CAND, NEW, RATES)
    assert m["objective"] == pytest.approx(h["objective"], abs=1e-6)
    assert m["objective"] == pytest.approx(brute_force(site, REQS, CAND, capacity=False), abs=1e-6)
    assert m["upgrades"] == {}


def test_new_poc_chosen_when_cheaper_than_long_run():
    site = tiny_site(400.0, 400.0)
    res = A.solve(site, REQS, CAND, NEW, RATES)
    # r0: new POC 3.0 m (780 + 6000) is dearer than P3 at 5.4 m (1404), so the existing POC wins ...
    assert res["assign"][0] == "P3" and res["new_pocs"] == []
    cand = {0: {"P1": 41.0, "H2-N012@0": 3.0}, 1: CAND[1], 2: CAND[2]}
    res2 = A.solve(site, REQS, cand, NEW, RATES)
    # ... but beats a 41 m run (10660 vs 6780)
    assert res2["assign"][0] == "H2-N012@0" and res2["new_pocs"] == ["H2-N012@0"]


def test_unserved_requirement_reported():
    site = tiny_site()
    cand = {0: {"P1": 4.0}, 1: {"P1": 5.0}, 2: {"P3": 6.0}}
    res = A.solve(site, REQS, cand, {}, RATES)
    assert len(res["unassigned"]) == 1 and res["unassigned"][0] in (0, 1)
    assert set(res["assign"].values()) == {"P1", "P3"}


def test_greedy_never_beats_milp_and_can_be_worse():
    site = tiny_site(100.0, 70.0)
    g = A.greedy(site, REQS, CAND, NEW, RATES)
    m = A.solve(site, REQS, CAND, NEW, RATES)
    assert m["objective"] <= g["objective"] + 1e-9
    site2 = tiny_site(58.0, 300.0)   # H1 has 3 L/min left after the existing 55
    cand = {0: {"P1": 3.0, "P3": 3.6}, 1: {"P4": 4.2}, 2: {"P2": 7.8}}
    g2 = A.greedy(site2, REQS, cand, {}, RATES)
    m2 = A.solve(site2, REQS, cand, {}, RATES)
    assert g2["upgrades"] == {"H1": 2} and m2["upgrades"] == {"H1": 1}
    assert m2["assign"][0] == "P3"
    assert m2["objective"] < g2["objective"]


def test_header_loads_only_count_built_hookups():
    site = tiny_site()
    site["hookups"].append({"id": "HN-N01-PCWS", "tool": "T-N01", "system": "PCWS", "poc": "P1",
                            "status": "planned", "size": "NPS 1", "points": []})
    assert header_loads(site) == {"H1": 55.0, "H2": 0.0}


def test_capacity_check_shortfall_and_reserve():
    site = tiny_site(100.0, 70.0)
    res = capacity_check(site)
    s = res["systems"][0]
    assert s["system"] == "PCWS"
    assert s["remaining"] == pytest.approx(100 + 70 - 55)
    assert s["new_load"] == pytest.approx(114.0)
    assert s["status"] == "OK" and s["margin"] == pytest.approx(1.0)
    r = capacity_check(site, reserve=0.1)["systems"][0]
    assert r["remaining"] == pytest.approx(153 - 55)
    assert r["status"] == "SHORTFALL"
    assert r["min_upgrade_steps"] == 1 and r["min_upgrade_cost"] == pytest.approx(5000.0)
    r3 = capacity_check(site, reserve=0.25)["systems"][0]
    assert r3["min_upgrade_steps"] == 2   # shortfall 41.5 -> two 40-unit steps
    only = capacity_check(site, tools=["T-N02"])["systems"][0]
    assert only["new_load"] == pytest.approx(38.0) and only["new_connections"] == 1
    with pytest.raises(ValueError):
        capacity_check(site, reserve=1.0)


def test_greedy_adds_as_many_steps_as_needed():
    site = tiny_site(58.0, 300.0)      # H1: 3 left
    reqs = [{"tool": "T-N01", "system": "PCWS", "flow": 95.0}]
    g = A.greedy(site, reqs, {0: {"P1": 2.4}}, {}, RATES)
    assert g["upgrades"] == {"H1": 3}  # 92 short -> three 40-unit steps


@pytest.mark.parametrize("reserve", [0.15, 0.3])
def test_milp_applies_reserve(reserve):
    site = tiny_site(160.0, 90.0)
    res = A.solve(site, REQS, CAND, NEW, RATES, reserve=reserve)
    scaled = tiny_site(160.0 * (1 - reserve), 90.0 * (1 - reserve))
    assert res["objective"] == pytest.approx(brute_force(scaled, REQS, CAND), abs=1e-6)
    assert res["objective"] > A.solve(site, REQS, CAND, NEW, RATES)["objective"]


# --- PCW supply/return pairing ---------------------------------------------------------------
PRATES = {"assignment_cost_per_m": {"PCWS": 260.0, "PCWR": 260.0}, "new_poc_each": 6000.0}


def pcw_site():
    hdr = lambda i, sysc, corr: {"id": i, "system": sysc, "corridor": corr, "y": 3.0, "z": 1.8, "x0": 1.2, "x1": 30.0,
                                 "od": 0.17, "capacity": 1000.0, "pressure_kpa_g": 520.0 if sysc == "PCWS" else 150.0,
                                 "upgrade_step": 40.0, "upgrade_cost": 5000.0, "upgrade_days": 5.0}
    poc = lambda i, h, sysc: {"id": i, "header": h, "system": sysc, "x": 3.0, "y": 3.0, "z": 1.8, "size": "NPS 1",
                              "rated_flow": 300.0, "status": "free"}
    return {"meta": {}, "columns": [], "equipment": [], "systems": [], "hookups": [],
            "headers": [hdr("S-A", "PCWS", "A"), hdr("S-B", "PCWS", "B"), hdr("R-A", "PCWR", "A"), hdr("R-B", "PCWR", "B")],
            "pocs": [poc("SA1", "S-A", "PCWS"), poc("SB1", "S-B", "PCWS"), poc("RA1", "R-A", "PCWR"),
                     poc("RB1", "R-B", "PCWR"), poc("SA2", "S-A", "PCWS"), poc("RB2", "R-B", "PCWR")],
            "tools": [{"id": "T-N01", "status": "new"}, {"id": "T-N02", "status": "new"}],
            "demands": []}


PREQS = [{"tool": "T-N01", "system": "PCWS", "flow": 40.0}, {"tool": "T-N01", "system": "PCWR", "flow": 40.0},
         {"tool": "T-N02", "system": "PCWS", "flow": 30.0}, {"tool": "T-N02", "system": "PCWR", "flow": 30.0}]
# unpaired optimum: T-N01 S on A (2 m) with R on B (2 m); T-N02 takes what is left
PCAND = {0: {"SA1": 2.0, "SB1": 9.0}, 1: {"RA1": 8.0, "RB1": 2.0}, 2: {"SA2": 3.0, "SB1": 4.0},
         3: {"RA1": 6.0, "RB2": 3.0}}


def pcw_brute(site, pairing):
    corr = {p["id"]: p["header"][-1] for p in site["pocs"]}
    best = math.inf
    for ch in itertools.product(*[list(PCAND[r]) for r in range(4)]):
        if len(set(ch)) < 4:
            continue
        if pairing and (corr[ch[0]] != corr[ch[1]] or corr[ch[2]] != corr[ch[3]]):
            continue
        best = min(best, sum(260.0 * PCAND[r][c] for r, c in enumerate(ch)))
    return best


def test_pcw_pairing_constraint_matches_brute_force():
    site = pcw_site()
    assert A.pcw_pairs(PREQS) == [(0, 1), (2, 3)]
    paired = A.solve(site, PREQS, PCAND, {}, PRATES)
    free = A.solve(site, PREQS, PCAND, {}, PRATES, pairing=False)
    assert paired["objective"] == pytest.approx(pcw_brute(site, True), abs=1e-6)
    assert free["objective"] == pytest.approx(pcw_brute(site, False), abs=1e-6)
    assert free["objective"] < paired["objective"]
    corr = lambda p: A.corridor(site, {}, p)
    assert corr(free["assign"][0]) != corr(free["assign"][1])        # unpaired model splits T-N01
    for s, t in A.pcw_pairs(PREQS):
        assert corr(paired["assign"][s]) == corr(paired["assign"][t])


def test_pcw_pair_left_unserved_together():
    site = pcw_site()
    cand = {0: {"SA1": 2.0}, 1: {"RB1": 2.0}, 2: {"SA2": 3.0}, 3: {"RA1": 6.0}}
    res = A.solve(site, PREQS, cand, {}, PRATES)
    assert sorted(res["unassigned"]) == [0, 1]
    assert res["assign"] == {2: "SA2", 3: "RA1"}


def test_greedy_keeps_pcw_return_on_supply_corridor():
    site = pcw_site()
    g = A.greedy(site, PREQS, PCAND, {}, PRATES)
    assert g["unassigned"] == [3]        # RA1 went to T-N01, and T-N02's supply took corridor A
    corr = lambda p: A.corridor(site, {}, p)
    for s, t in A.pcw_pairs(PREQS):
        if t in g["assign"]:
            assert corr(g["assign"][s]) == corr(g["assign"][t])
    assert g["assign"][0] == "SA1" and g["assign"][1] == "RA1"
