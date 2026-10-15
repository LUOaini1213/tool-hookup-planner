import pytest

from hookup_planner import costing, schedule
from hookup_planner.numfmt import cell, r10, write_csv


def test_hookup_cost_hand_calculation(rates):
    hk = {"id": "HN-N01-CDA", "tool": "T-N01", "system": "CDA", "size": "OD 3/4 in", "length_m": 12.5, "bends": 3}
    c = costing.hookup_cost(rates, hk)
    assert c["material"] == pytest.approx(12.5 * (28 + 2.2 * 19.05))
    assert c["fittings"] == pytest.approx(3 * (15 + 0.6 * 19.05))
    assert c["labour_h"] == pytest.approx(12.5 * 1.1)
    assert c["labour"] == pytest.approx(12.5 * 1.1 * 60)
    assert c["tie_in"] == 1100 and c["test"] == 550
    assert c["total"] == pytest.approx(c["material"] + c["fittings"] + c["labour"] + 1100 + 550)
    p = costing.hookup_cost(rates, {"id": "HN-N01-PWR", "tool": "T-N01", "system": "PWR", "size": "63 A",
                                    "length_m": 7.3, "bends": 4})
    assert p["material"] == pytest.approx(7.3 * (6 + 0.08 * 63))
    assert p["fittings"] == 0.0
    d = costing.hookup_cost(rates, {"id": "HN-N02-SEX", "tool": "T-N02", "system": "SEX", "size": "D250",
                                    "length_m": 9.1, "bends": 2})
    assert d["material"] == pytest.approx(9.1 * (20 + 1.6 * 250))
    assert d["labour_h"] == pytest.approx(9.1 * 0.7)


def test_take_off_groups_by_system_and_size():
    hks = [{"system": "N2", "size": "OD 1/2 in", "length_m": 4.2, "bends": 2},
           {"system": "N2", "size": "OD 1/2 in", "length_m": 7.9, "bends": 5},
           {"system": "N2", "size": "OD 3/4 in", "length_m": 3.3, "bends": 1},
           {"system": "PWR", "size": "100 A", "length_m": 6.1, "bends": 3}]
    mto = costing.take_off(hks)
    assert [(m["category"], m["system"], m["size"]) for m in mto] == [
        ("cable", "PWR", "100 A"), ("pipe", "N2", "OD 1/2 in"), ("pipe", "N2", "OD 3/4 in")]
    assert mto[1]["length_m"] == pytest.approx(12.1) and mto[1]["elbows"] == 7 and mto[1]["hookups"] == 2
    assert mto[0]["elbows"] == 0


def test_estimate_includes_lateral_work(rates, small_plan):
    up = {"PCWS-A": 2}
    est = costing.estimate(rates, small_plan["hookups"], up, small_plan["site"])
    hdr = next(h for h in small_plan["site"]["headers"] if h["id"] == "PCWS-A")
    n_new = len({h["poc"] for h in small_plan["hookups"] if h["new_poc"]})
    assert est["pls_total"] == pytest.approx(2 * hdr["upgrade_cost"] + n_new * rates["new_poc_each"])
    assert est["grand_total"] == pytest.approx(est["hookup_total"] + est["pls_total"])
    assert est["hookup_total"] == pytest.approx(sum(est["by_system"].values()))


def test_slots_round_up_to_half_days():
    assert schedule.slots(0.01) == 1
    assert schedule.slots(1.0) == 2
    assert schedule.slots(1.26) == 3
    assert schedule.slots(0.0) == 1


def test_serial_sgs_hand_case():
    tasks = [{"id": "LH-X", "tool": "", "type": "LH", "resource": "pls", "dur": 6, "preds": []},
             {"id": "HU-a", "tool": "T1", "type": "HU", "resource": "pipe", "dur": 3, "preds": ["LH-X"]},
             {"id": "HU-b", "tool": "T1", "type": "HU", "resource": "pipe", "dur": 5, "preds": []},
             {"id": "HU-c", "tool": "T2", "type": "HU", "resource": "pipe", "dur": 2, "preds": []},
             {"id": "TS-a", "tool": "T1", "type": "TS", "resource": "test", "dur": 1, "preds": ["HU-a"]},
             {"id": "UO-T1", "tool": "T1", "type": "UO", "resource": "", "dur": 2, "preds": ["TS-a", "HU-b"]}]
    out = {t["id"]: (t["start"], t["finish"]) for t in schedule.serial_sgs(tasks, {"pipe": 1, "test": 1,
                                                                                  "pls": 1})}
    assert out["LH-X"] == (0, 6)
    assert out["HU-b"] == (0, 5)          # T1 before T2; HU-a must wait for LH-X
    assert out["HU-a"] == (6, 9)
    assert out["HU-c"] == (9, 11)         # one pipe crew: queued behind T1's work
    assert out["TS-a"] == (9, 10)
    assert out["UO-T1"] == (10, 12)
    two = {t["id"]: t["start"] for t in schedule.serial_sgs(tasks, {"pipe": 2, "test": 1, "pls": 1})}
    assert two["HU-c"] == 0


def test_schedule_respects_precedence_and_crews(rates, small_plan):
    sch = schedule.schedule(rates, small_plan["hookups"], {"AEX-B": 1}, small_plan["site"])
    tasks = {t["id"]: t for t in sch["tasks"]}
    for t in tasks.values():
        for p in filter(None, t["preds"].split(";")):
            assert tasks[p]["finish_day"] <= t["start_day"]
    crews = rates["schedule"]["crews"]
    horizon = int(sch["makespan_days"] * 2)
    for res, cap in crews.items():
        for s in range(horizon):
            busy = sum(1 for t in tasks.values() if t["resource"] == res and t["start_day"] * 2 <= s < t["finish_day"] * 2)
            assert busy <= cap
    aex = [t for t in tasks.values() if t["id"].startswith("HU-") and t["id"].endswith("-AEX")]
    if any(h["header"] == "AEX-B" for h in small_plan["hookups"] if h["system"] == "AEX"):
        assert any("LH-AEX-B" in t["preds"] for t in aex)
    assert sch["makespan_days"] == max(sch["startup_done_day"].values())


def test_gantt_png_written(rates, small_plan, tmp_path):
    sch = schedule.schedule(rates, small_plan["hookups"], {}, small_plan["site"])
    p = tmp_path / "g.png"
    schedule.gantt_png(sch, p)
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_r10_and_csv_formatting(tmp_path):
    assert r10(0.1 + 0.2) == 0.3
    assert r10(589.8000000000001) == 589.8
    assert r10(-0.0) == 0.0 and r10(3) == 3 and r10(True) is True
    assert cell(1.23456789012345) == "1.23456789"
    assert cell(None) == "" and cell(False) == "false"
    with pytest.raises(ValueError):
        r10(float("nan"))
    write_csv(tmp_path / "x.csv", ["a", "b"], [[1.0000000000049, "x"]])
    assert (tmp_path / "x.csv").read_bytes() == b"a,b\n1.0,x\n"


def test_slots_never_round_down():
    assert schedule.slots(1.1) == 3
    assert schedule.slots(2.74) == 6


def test_schedule_has_move_in_utilities_on_and_startup(rates, small_plan):
    sch = schedule.schedule(rates, small_plan["hookups"], {}, small_plan["site"])
    tasks = {t["id"]: t for t in sch["tasks"]}
    for tool in {h["tool"] for h in small_plan["hookups"]}:
        ms, uo, vs = tasks[f"MS-{tool}"], tasks[f"UO-{tool}"], tasks[f"VS-{tool}"]
        assert ms["resource"] == "rigging" and ms["duration_days"] == 1.5
        tests = [t for t in tasks.values() if t["type"] == "TS" and t["tool"] == tool]
        assert tests and all(f"MS-{tool}" in t["preds"].split(";") for t in tests)
        assert all(ms["finish_day"] <= t["start_day"] and t["finish_day"] <= uo["start_day"] for t in tests)
        assert vs["start_day"] >= uo["finish_day"] and vs["duration_days"] == 5.0
        assert sch["utilities_on_day"][tool] == uo["finish_day"]
    assert sch["last_utilities_on_day"] == max(sch["utilities_on_day"].values()) < sch["makespan_days"]
