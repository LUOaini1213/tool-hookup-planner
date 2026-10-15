import json

import pytest

from hookup_planner import engineering as E
from hookup_planner.geometry import box_gap
from hookup_planner.model import Index, evaluate_hookup, header_loads, static_solids
from hookup_planner.numfmt import dumps
from hookup_planner.planner import plan


def test_every_requirement_routed_without_clashes(small_plan):
    reqs = small_plan["requirements"]
    assert len(reqs) >= 15
    assert small_plan["failures"] == []
    assert len(small_plan["hookups"]) == len(reqs)
    assert small_plan["clashes"] == []
    assert len(small_plan["naive_clashes"]) > 0


def test_routes_connect_poc_to_tool_and_are_orthogonal(small_plan):
    site = small_plan["site"]
    idx = Index(site)
    m = site["meta"]
    for hk in small_plan["hookups"]:
        pts = hk["points"]
        poc = idx.pocs[hk["poc"]]
        d = idx.demand[(hk["tool"], hk["system"])]
        assert pts[0] == pytest.approx([poc["x"], poc["y"], poc["z"]])
        assert pts[-1] == pytest.approx([d["px"], d["py"], E.FAB_FLOOR_Z])
        for a, b in zip(pts, pts[1:]):
            assert sum(abs(a[t] - b[t]) > 1e-9 for t in range(3)) == 1
        for p in pts[1:-1]:
            assert m["kmin"] * m["step"] - 1e-9 <= p[2] <= (m["kmax"] + 1) * m["step"] + 1e-9
        assert hk["length_m"] >= abs(pts[0][0] - pts[-1][0]) + abs(pts[0][1] - pts[-1][1]) + \
            abs(pts[0][2] - pts[-1][2]) - 1e-9


def test_routes_keep_clearance_from_static_obstacles_independently(small_plan):
    site = small_plan["site"]
    idx = Index(site)
    solids = static_solids(site)
    for hk in small_plan["hookups"]:
        r = E.size_by_label(hk["system"], hk["size"])["od"] / 2
        own = idx.pocs[hk["poc"]]["header"]
        pts = hk["points"]
        for n, (a, b) in enumerate(zip(pts, pts[1:])):
            lo = [min(a[t], b[t]) for t in range(3)]
            hi = [max(a[t], b[t]) for t in range(3)]
            for s in solids:
                if n == 0 and s.eid == own:
                    continue
                gap = box_gap(lo, hi, s.lo, s.hi) - r - s.r
                assert gap >= E.CLEARANCE_M - 1e-9, (hk["id"], s.eid, gap)


def test_hookup_checks_recomputed_from_geometry(small_plan):
    site = small_plan["site"]
    idx = Index(site)
    for hk in small_plan["hookups"]:
        ev = evaluate_hookup(site, hk["system"], hk["flow"], hk["tool_p_kpa_g"], idx.pocs[hk["poc"]], hk["points"],
                             hk["size"])
        assert ev["ok"], hk["id"]
        assert ev["length_m"] == pytest.approx(hk["length_m"])
        if ev["dp_total_kpa"] is not None:
            assert ev["dp_total_kpa"] == pytest.approx(hk["dp_total_kpa"])
            assert ev["velocity"] <= E.SYSTEMS[hk["system"]]["v_max"]
        n = E.size_index(hk["system"], hk["size"])
        if n > 0:
            smaller = E.sizes_for(hk["system"])[n - 1]["label"]
            assert not evaluate_hookup(site, hk["system"], hk["flow"], hk["tool_p_kpa_g"], idx.pocs[hk["poc"]],
                                       hk["points"], smaller)["ok"], hk["id"]


def test_assignment_respects_systems_ratings_and_capacity(small_plan):
    site = small_plan["site"]
    idx = Index(site)
    hk = small_plan["hookups"]
    assert len({h["poc"] for h in hk}) == len(hk)
    used_before = {h["poc"] for h in site["hookups"]}
    for h in hk:
        poc = idx.pocs[h["poc"]]
        assert poc["system"] == h["system"]
        assert poc["rated_flow"] >= h["flow"]
        assert h["poc"] not in used_before
    loads = header_loads(site)
    ups = small_plan["assignment"]["milp"]["upgrades"]
    for hdr in site["headers"]:
        new = sum(h["flow"] for h in hk if h["header"] == hdr["id"])
        assert loads[hdr["id"]] + new <= hdr["capacity"] + ups.get(hdr["id"], 0) * hdr["upgrade_step"] + 1e-9


def test_milp_not_worse_than_greedy_and_matches_hungarian(small_plan):
    a = small_plan["assignment"]
    assert a["milp"]["objective"] <= a["greedy"]["objective"] + 1e-6
    assert a["milp_relaxed"]["objective"] == pytest.approx(a["hungarian_relaxed"]["objective"], abs=1e-6)
    assert a["milp_relaxed"]["objective"] <= a["milp"]["objective"] + 1e-6


def test_plan_is_deterministic(small_site, small_plan, rates):
    again = plan(small_site, rates)
    assert dumps(again["hookups"]) == dumps(small_plan["hookups"])
    assert json.dumps(again["assignment"]["milp"]["assign"]) == json.dumps(small_plan["assignment"]["milp"]["assign"])


def test_plan_does_not_mutate_input(small_site, rates):
    before = dumps(small_site)
    plan(small_site, rates)
    assert dumps(small_site) == before


def test_own_header_exempt_only_for_take_off():
    from hookup_planner.geometry import Solid, find_clashes, polyline_solids
    from hookup_planner.planner import own_header_exempt
    site = {"pocs": [{"id": "P1", "header": "H"}]}
    hdr = [Solid("H", "header", (0, 3, 1.8), (9, 3, 1.8), 0.1, "H")]
    ok = polyline_solids("HK", [(3, 3, 1.8), (3, 3, 2.4), (5.4, 3, 2.4)], 0.02, meta={"poc": "P1"})
    bad = polyline_solids("HK2", [(3.6, 3, 1.8), (3.6, 3, 2.4), (4.8, 3, 2.4), (4.8, 3, 1.2)], 0.02,
                          meta={"poc": "P1"})
    ex = own_header_exempt(site)
    assert find_clashes(ok, hdr, 0.05, ex) == []
    cl = find_clashes(bad, hdr, 0.05, ex)
    assert [c["a"] for c in cl] == ["HK2#2"]


def test_take_off_columns_reserved(small_plan, small_site):
    from hookup_planner.model import build_lattice
    from hookup_planner.planner import reserve_takeoffs
    site = small_plan["site"]
    lat = build_lattice(dict(site, hookups=[h for h in site["hookups"] if h["status"] != "planned"]))
    chosen = small_plan["assignment"]["milp"]["assign"]
    nodes = reserve_takeoffs(lat, site, small_plan["requirements"], chosen, small_plan["new_poc_specs"])
    assert len(nodes) >= len(chosen)
    m = lat.free_mask(0.01, 0.05)
    assert all(m[n] == 0 for n in nodes)


def test_route_is_redone_when_pressure_grows_the_size(small_site):
    from hookup_planner.model import build_lattice, route_one
    d = next(x for x in small_site["demands"] if x["tool"].startswith("T-N") and x["system"] == "PCWS")
    far = max((p for p in small_site["pocs"] if p["system"] == "PCWS" and p["status"] == "free"),
              key=lambda p: (abs(p["x"] - d["px"]) + abs(p["y"] - d["py"]), p["id"]))
    for p_req, governed, calls_expected in ((300.0, "velocity", 1), (458.0, "pressure", 2)):
        lat = build_lattice(small_site)
        calls = []
        orig = lat.astar
        lat.astar = lambda *a, **k: calls.append(1) or orig(*a, **k)
        res = route_one(small_site, lat, "PCWS", d["flow"], p_req, far, (d["px"], d["py"]))
        assert res["governed_by"] == governed
        assert len(calls) == calls_expected


def test_pcw_supply_and_return_share_a_corridor_and_close_the_loop(small_plan):
    site = small_plan["site"]
    idx = Index(site)
    hk = {(h["tool"], h["system"]): h for h in small_plan["hookups"]}
    tools = sorted(t for t, s in hk if s == "PCWR")
    assert tools
    for t in tools:
        s, r = hk[(t, "PCWS")], hk[(t, "PCWR")]
        assert s["corridor"] == r["corridor"]
        p_s = idx.headers[s["header"]]["pressure_kpa_g"]
        p_r = idx.headers[r["header"]]["pressure_kpa_g"]
        outlet = p_s - s["dp_total_kpa"] - idx.demand[(t, "PCWR")]["p_req"]
        assert r["tool_p_kpa_g"] == pytest.approx(outlet)
        assert r["available_dp_kpa"] == pytest.approx(outlet - p_r)
        assert outlet - r["dp_total_kpa"] >= p_r - 1e-9
    a = small_plan["assignment"]
    assert a["milp_no_pairing"]["objective"] <= a["milp"]["objective"] + 1e-6


def test_candidates_exclude_pocs_rated_below_the_demand(small_plan):
    site = small_plan["site"]
    idx = Index(site)
    excluded = 0
    for r, d in enumerate(small_plan["requirements"]):
        for k in small_plan["candidates"][r]:
            if "@" not in k:
                assert idx.pocs[k]["system"] == d["system"]
                assert idx.pocs[k]["rated_flow"] >= d["flow"], (d["tool"], d["system"], k)
        excluded += sum(1 for p in site["pocs"] if p["system"] == d["system"] and p["status"] == "free"
                        and p["rated_flow"] < d["flow"])
    assert excluded > 0          # the filter has something to exclude in this fixture
