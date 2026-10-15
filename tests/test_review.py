import copy
import random

import pytest

from hookup_planner import review as R


@pytest.fixture(scope="module")
def proposal(small_plan):
    return [{k: h[k] for k in ("id", "tool", "system", "poc", "size", "points")} for h in small_plan["hookups"]]


def codes(issues, hk=None):
    return {i["code"] for i in issues if hk is None or i["hookup"] == hk}


def test_clean_plan_has_no_findings(small_plan, proposal):
    assert R.review(small_plan["site"], proposal, small_plan["assignment"]["milp"]["upgrades"]) == []


@pytest.fixture(scope="module")
def evaluation(small_plan, proposal):
    return R.evaluate_faults(small_plan["site"], proposal, small_plan["assignment"]["milp"]["upgrades"], per_fault=5)


def test_check_coverage_every_rule_fault_fires_its_rule(small_plan, evaluation):
    assert evaluation["clean_issues"] == 0
    for fault, res in evaluation["rule_faults"].items():
        if fault == "header_over_capacity" and not small_plan["assignment"]["milp"]["upgrades"]:
            continue
        assert res["injected"] >= 1, fault
        assert res["expected_fired"] == res["injected"], fault
        assert res["unexplained_elsewhere"] == 0, fault
        assert set(res["codes_on_target"]) >= set(res["expected_codes"]) & set(res["codes_on_target"])


def test_open_faults_are_reported_honestly(evaluation):
    of = evaluation["open_faults"]
    assert set(of) == set(R.OPEN_FAULTS)
    # oversized lines (flow in L/min read as m3/h) are not flagged by any check
    assert of["unit_lpm_read_as_m3h"]["injected"] >= 1 and of["unit_lpm_read_as_m3h"]["caught"] == 0
    # undersized lines (m3/h read as L/min) trip the velocity check
    m3h = of["unit_m3h_read_as_lpm"]
    assert m3h["caught"] == m3h["injected"] >= 1 and "UNDERSIZED_VELOCITY" in m3h["codes_on_target"]
    for f in ("supply_return_swapped", "route_to_wrong_tool"):
        assert of[f]["caught"] == of[f]["injected"] >= 1, f
        assert "ROUTE_DISCONNECTED" in of[f]["codes_on_target"], f
    for f in of.values():
        assert f["caught"] == sum(c["caught"] for c in f["cases"])


def test_gas_dp_fault_trips_model_validity(small_plan, proposal):
    from hookup_planner import engineering as E
    from hookup_planner import hydraulics as H
    from hookup_planner.lattice import bends, length
    site = copy.deepcopy(small_plan["site"])
    prop = copy.deepcopy(proposal)
    t = next(n for n, h in enumerate(prop) if h["system"] == "N2")
    hk = prop[t]
    # a heavy N2 user drawn in 2 in tube: the fault picks the largest smaller tube that breaks 10 %
    d = next(x for x in site["demands"] if x["tool"] == hk["tool"] and x["system"] == "N2")
    d["flow"] = 150.0
    hk["size"] = "OD 2 in"
    assert R.inject(site, prop, {}, "gas_dp_over_10pct", next(n for n, h in enumerate(prop) if h["system"] == "PCWS"),
                    random.Random(1)) is None
    out, _, ids = R.inject(site, prop, {}, "gas_dp_over_10pct", t, random.Random(1))
    new = out[t]["size"]
    pts = [tuple(p) for p in hk["points"]]
    dp = lambda lab: H.line_loss("N2", 150.0, E.size_by_label("N2", lab)["id"], length(pts), bends(pts),
                                 6.6 - pts[0][2], 700.0)["dp_total_kpa"]
    n = E.size_index("N2", new)
    assert dp(new) >= 0.1 * 801.325 > dp(E.sizes_for("N2")[n + 1]["label"])
    assert "MODEL_INVALID" in codes(R.review(site, out), ids[0])


def test_redirected_route_ends_at_new_point_and_stays_orthogonal(proposal):
    pts = proposal[0]["points"]
    new = R._redirect_end(pts, pts[-1][0] + 1.2, pts[-1][1] + 0.6)
    assert new[-1] == pytest.approx([pts[-1][0] + 1.2, pts[-1][1] + 0.6, 6.6])
    for a, b in zip(new, new[1:]):
        assert sum(abs(a[k] - b[k]) > 1e-9 for k in range(3)) == 1


def test_pcw_split_corridor_and_loop_checks(small_plan, proposal):
    site = copy.deepcopy(small_plan["site"])
    sup = next(h for h in proposal if h["system"] == "PCWS")
    ret = next(h for h in proposal if h["system"] == "PCWR" and h["tool"] == sup["tool"])
    # return moved to a free PCWR POC on the other corridor
    corr = {h["id"]: h["corridor"] for h in site["headers"]}
    here = corr[next(p["header"] for p in site["pocs"] if p["id"] == ret["poc"])]
    other = next(p for p in site["pocs"] if p["system"] == "PCWR" and p["status"] == "free"
                 and corr[p["header"]] != here and p["id"] not in {h["poc"] for h in proposal})
    prop = copy.deepcopy(proposal)
    next(h for h in prop if h["id"] == ret["id"])["poc"] = other["id"]
    iss = R.review(site, prop)
    assert "PCW_SPLIT_CORRIDOR" in codes(iss, ret["id"]) and "PCW_SPLIT_CORRIDOR" in codes(iss, sup["id"])
    # without its supply in the proposal, the return's loop cannot be checked
    iss = R.review(site, [h for h in proposal if h["id"] != sup["id"]])
    assert codes(iss, ret["id"]) == {"PCW_LOOP_UNVERIFIED"}
    # a tool pressure drop that leaves too little for the return fails the loop on the return
    d = next(x for x in site["demands"] if x["tool"] == ret["tool"] and x["system"] == "PCWR")
    d["p_req"] = 380.0
    iss = R.review(site, proposal)
    assert codes(iss, ret["id"]) == {"UNDERSIZED_PRESSURE"}
    detail = next(i["detail"] for i in iss if i["hookup"] == ret["id"])
    plan_s = next(h for h in small_plan["hookups"] if h["id"] == sup["id"])
    avail = 520.0 - plan_s["dp_total_kpa"] - 380.0 - 150.0
    assert "PCW loop" in detail and f"available {avail:.4g} kPa" in detail
    assert codes(iss, sup["id"]) == set()


def test_supply_return_swap_redirects_both_ends(small_plan, proposal):
    site = small_plan["site"]
    t = next(n for n, h in enumerate(proposal) if h["system"] == "PCWS")
    prop, _, ids = R.inject(site, proposal, {}, "supply_return_swapped", t, random.Random(3))
    dem = {(d["tool"], d["system"]): d for d in site["demands"]}
    s = next(h for h in prop if h["id"] == ids[0])
    r = next(h for h in prop if h["id"] == ids[1])
    assert (s["system"], r["system"]) == ("PCWS", "PCWR") and s["tool"] == r["tool"]
    assert s["points"][-1][:2] == pytest.approx([dem[(r["tool"], "PCWR")]["px"], dem[(r["tool"], "PCWR")]["py"]])
    assert r["points"][-1][:2] == pytest.approx([dem[(s["tool"], "PCWS")]["px"], dem[(s["tool"], "PCWS")]["py"]])
    iss = R.review(site, prop)
    assert "ROUTE_DISCONNECTED" in codes(iss, ids[0]) and "ROUTE_DISCONNECTED" in codes(iss, ids[1])


def test_wrong_utility_and_disconnection(small_plan, proposal):
    site = small_plan["site"]
    prop = copy.deepcopy(proposal)
    hk = next(h for h in prop if h["system"] == "CDA")
    n2 = next(p for p in site["pocs"] if p["system"] == "N2" and p["status"] == "free")
    hk["poc"] = n2["id"]
    iss = R.review(site, prop)
    assert {"WRONG_UTILITY", "ROUTE_DISCONNECTED"} <= codes(iss, hk["id"])
    assert "UNDERSIZED_VELOCITY" not in codes(iss, hk["id"])


def test_poc_already_serving_existing_tool(small_plan, proposal):
    site = small_plan["site"]
    prop = copy.deepcopy(proposal)
    hk = prop[0]
    taken = next(h for h in site["hookups"] if h["system"] == hk["system"])
    hk["poc"] = taken["poc"]
    assert "POC_IN_USE" in codes(R.review(site, prop), hk["id"])


def test_header_capacity_depends_on_declared_upgrades(small_plan, proposal):
    site = copy.deepcopy(small_plan["site"])
    hk = proposal[0]
    hdr_id = next(p["header"] for p in site["pocs"] if p["id"] == hk["poc"])
    hdr = next(h for h in site["headers"] if h["id"] == hdr_id)
    from hookup_planner.model import header_loads
    load = header_loads(site)[hdr_id]
    new = sum(next(d["flow"] for d in site["demands"] if d["tool"] == h["tool"] and d["system"] == h["system"])
              for h in proposal if next(p["header"] for p in site["pocs"] if p["id"] == h["poc"]) == hdr_id)
    hdr["capacity"] = load + new - 0.5 - hdr["upgrade_step"]       # short even with one step less
    hdr["upgrade_step"] = hdr["upgrade_step"]
    without = R.review(site, proposal, {})
    assert "HEADER_OVER_CAPACITY" in codes(without, hk["id"])
    one = R.review(site, proposal, {hdr_id: 1})
    assert "HEADER_OVER_CAPACITY" in codes(one, hk["id"])
    two = R.review(site, proposal, {hdr_id: 2})
    assert "HEADER_OVER_CAPACITY" not in codes(two)


def test_undersized_line_flags_the_failing_check(small_plan, proposal):
    from hookup_planner import engineering as E
    site = small_plan["site"]
    for h in small_plan["hookups"]:
        n = E.size_index(h["system"], h["size"])
        if n == 0:
            continue
        prop = copy.deepcopy(proposal)
        tgt = next(p for p in prop if p["id"] == h["id"])
        tgt["size"] = E.sizes_for(h["system"])[n - 1]["label"]
        c = codes(R.review(site, prop), h["id"])
        if h["governed_by"] == "velocity":
            assert "UNDERSIZED_VELOCITY" in c, h["id"]
        elif h["governed_by"] == "rating":
            assert c == {"UNDERSIZED_RATING"}, h["id"]
        else:
            assert c & {"UNDERSIZED_PRESSURE", "MODEL_INVALID"}, h["id"]


def test_bad_references_and_geometry(small_plan, proposal):
    site = small_plan["site"]
    prop = copy.deepcopy(proposal)
    prop[0]["poc"] = "NOPE-P99"
    prop[1]["size"] = "NPS 9"
    prop[2]["points"] = [prop[2]["points"][0], [1.0, 2.0, 3.0]]
    iss = R.review(site, prop)
    assert codes(iss, prop[0]["id"]) == {"UNKNOWN_REFERENCE"}
    assert codes(iss, prop[1]["id"]) == {"UNKNOWN_REFERENCE"}
    assert "ROUTE_NOT_ORTHOGONAL" in codes(iss, prop[2]["id"])


def test_clash_injection_hits_a_column(small_plan, proposal):
    inj = R.inject(small_plan["site"], proposal, {}, "clash", 1, random.Random(5))
    prop, _, ids = inj
    iss = R.review(small_plan["site"], prop)
    hard = [i for i in iss if i["code"] == "CLASH_HARD" and i["hookup"] == ids[0]]
    assert any("column" in i["detail"] for i in hard)


def test_report_markdown(small_plan, proposal):
    assert "No issues found." in R.report_md([], "x")
    prop = copy.deepcopy(proposal)
    prop[0]["poc"] = "NOPE"
    md = R.report_md(R.review(small_plan["site"], prop), "Demo")
    assert md.startswith("# Demo") and "| UNKNOWN_REFERENCE | error | 1 |" in md
