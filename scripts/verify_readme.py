"""Check that every number quoted in README.md is the value in results/ (run from anywhere)."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"


def j(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def rows(name):
    with open(RES / name, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def money(x):
    return f"{round(float(x)):,} CU"


def pct(x):
    return f"{100 * float(x):.1f} %"


def main() -> int:
    s, a, r, c, sch, rt, ev = (j("summary.json"), j("assignment.json"), j("routing_summary.json"),
                               j("cost_summary.json"), j("schedule_summary.json"), j("roundtrip.json"),
                               j("review_eval.json"))
    cap = {x["system"]: x for x in rows("capacity_check.csv")}
    sens = rows("capacity_sensitivity.csv")
    s10 = next(x for x in sens if float(x["reserve"]) == 0.1)
    hk = rows("hookup_list.csv")
    mut_all = (RES / "mutation_report.txt").read_text(encoding="utf-8")
    mut = mut_all.strip().splitlines()[-1]
    n_tests = re.search(r"against (\d+) unit tests", mut_all).group(1)
    m_kill = re.match(r"(\d+)/(\d+) mutants killed \((\d+) documented equivalent, (\d+) escaped\)", mut)
    rf, of = ev["rule_faults"], ev["open_faults"]
    ms, mp, gr = a["milp"], a["milp_no_pairing"], a["greedy"]
    exh = [h for h in hk if h["system"] in ("GEX", "AEX", "SEX")]
    gas = [h for h in hk if h["system"] in ("CDA", "N2")]
    n_pwr_new = sum(1 for i in c["pls_items"] if i["item"].startswith("New POC PWR"))
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    expected = [
        f"ifc_equals_seed **{str(rt['ifc_equals_seed']).lower()}**",
        f"db_equals_seed **{str(rt['db_equals_seed']).lower()}**",
        f"({s['ifc_port_mismatches']} mismatches over {rt['ports_base']['hookups_checked']} hookups and "
        f"{rt['ports_base']['pocs_checked']} POCs)",
        f"{rt['counts']['columns']} columns, {rt['counts']['headers']} headers",
        f"{rt['counts']['pocs']} POCs, {s['tools_existing']} existing tools",
        f"{s['tools_new']} new tools",
        f"The {s['tools_new']} new tools need {s['requirements']} connections",
        f"AEX new load {float(cap['AEX']['new_load']):.0f} m³/h against {float(cap['AEX']['remaining']):.0f} m³/h",
        f"has a {float(cap['PCWS']['margin']):.0f} L/min margin ({100 * float(cap['PCWS']['utilisation_after']):.2f} %",
        f"split {mp['pcw_tools_split_across_corridors']} of the {a['pcw_tools']} PCW",
        f"pairing costs {ms['objective'] - mp['objective']:,.0f} CU",
        f"leaves {a['milp_existing_pocs_only']['unassigned']} requirements unserved (all "
        f"{'/'.join(a['milp_existing_pocs_only']['unassigned_systems'])})",
        f"serves\nall {s['requirements']}",
        f"| MILP | {money(ms['est_hookup_cost'])} | AEX-D ×1 | **{money(ms['objective'])}** |",
        f"| {money(gr['est_hookup_cost'])} | AEX-D ×1, PCWS-C ×1 | {money(gr['objective'])} |",
        f"{pct(s['milp_saving_vs_greedy_reserve0'])} at 0 %, {pct(s['milp_saving_vs_greedy_reserve10'])} at 10 %",
        f"between {pct(s['milp_saving_vs_greedy_range'][0])} and {pct(s['milp_saving_vs_greedy_range'][1])} over the "
        f"{len(sens)} reserves",
        f"spends {ms['est_hookup_cost'] - gr['est_hookup_cost']:,.0f} CU more on longer hookups",
        f"same optimum\n({money(a['milp_relaxed']['objective'])})",
        f"All {r['hookups']} hookups\nrouted, {r['routed_length_m']:.1f} m in total",
        f"{100 * (r['routed_over_lower_bound'] - 1):.2f} % above the Manhattan lower bound "
        f"({r['manhattan_lower_bound_m']:.1f} m), {r['bends']} bends",
        f"**{r['astar_clashes']} clashes**",
        f"the {rt['counts']['hookups']} existing hookups",
        f"produce {r['naive_clashes']} clashes on {r['naive_hookups_with_clash']} of the {r['hookups']} hookups",
        f"velocity limit for {r['sizes_governed_by']['velocity']} hookups, by the pressure budget for\n"
        f"{r['sizes_governed_by']['pressure']}",
        f"breaker\nrule for {r['sizes_governed_by']['rating']} power hookups",
        f"the {r['exhaust_hookups']}\nexhaust hookups lose {r['exhaust_dp_range_kpa'][0]:.3f} to "
        f"{r['exhaust_dp_range_kpa'][1]:.3f} kPa",
        f"the static term is at most\n{r['exhaust_static_abs_max_kpa']:.4f} kPa",
        f"the smallest loop margin is {r['pcwr_min_margin_kpa']:.1f} kPa",
        f"{r['exhaust_below_1000_fpm']} of the {r['exhaust_hookups']} exhaust hookups run below 1000 ft/min (see",
        f"{r['exhaust_below_1000_fpm']} of the {r['exhaust_hookups']} exhaust hookups run below 1000 ft/min, which",
        f"Estimate {money(c['grand_total'])}: hookups {money(c['hookup_total'])}, process lateral work "
        f"{money(c['pls_total'])}",
        f"(one AEX header\ncapacity step and {words[n_pwr_new]} new breakers)",
        f"{sch['tasks']} tasks",
        f"utilities turned on (handed to the vendor) on day {sch['last_utilities_on_day']:g}",
        f"tool ends on day {sch['makespan_days']:g}",
        f"own\nproposal gets {s['review_clean_issues']} findings",
        f"Only {rf['header_over_capacity']['injected']} header-over-capacity cases exist",
        f"of a faulted hookup: {sum(f['explained_elsewhere'] for f in rf.values())} in total) or unexplained "
        f"({sum(f['unexplained_elsewhere'] for f in rf.values())})",
        f"Only {of['gas_dp_over_10pct']['injected']} of the {len(gas)} gas hookups",
        f"`results/MANIFEST.sha256` ({len((RES / 'MANIFEST.sha256').read_text().splitlines())}\nfiles",
        f"The suite has {n_tests} tests",
        f"applies {m_kill.group(2)} deliberate bugs",
        f"{m_kill.group(1)}/{m_kill.group(2)} killed, {m_kill.group(3)} documented equivalent, "
        f"{m_kill.group(4)} escaped",
    ]
    for res_row, label in zip(sens, ("0 %", "2 %", "5 %", "10 %", "20 %")):
        expected.append(f"| {label} | {res_row['systems_short']} | {res_row['milp_upgrade_steps']} | "
                        f"{money(res_row['milp_upgrade_cost'])} |")
    labels = {"wrong_utility": "wrong utility at the POC", "undersized_line": "undersized line",
              "clash": "clash (detour through a column)", "poc_over_rating": "POC over rating",
              "header_over_capacity": "header over capacity (declared step removed)", "duplicate_poc": "duplicate POC",
              "disconnected_route": "disconnected route", "pcw_split_corridor": "PCW return on the other corridor"}
    for k, f in rf.items():
        expected.append(f"| {labels[k]} | {f['injected']} | {f['expected_fired']} |")
    olabels = {"unit_lpm_read_as_m3h": "flow in L/min read as m³/h when sizing (line oversized)",
               "unit_m3h_read_as_lpm": "flow in m³/h read as L/min when sizing (line undersized)",
               "gas_dp_over_10pct": "gas line with a loss over 10 % of inlet pressure",
               "supply_return_swapped": "PCW supply and return swapped at the tool",
               "route_to_wrong_tool": "route ending at another tool"}
    for k, f in of.items():
        caught = f"**{f['caught']}**" if f["caught"] == 0 else str(f["caught"])
        expected.append(f"| {olabels[k]} | {f['injected']} | {caught} |")
    # facts stated in words
    assert s["systems_short"] == ["AEX"], "README says only acid exhaust is short"
    assert r["all_checks_pass"] and not r["failures"]
    assert r["negative_dp_exhaust_hookups"] == 0, "README says every exhaust hookup loses pressure"
    assert r["pcw_tools_split_across_corridors"] == 0 and ms["pcw_tools_split_across_corridors"] == 0
    assert gr["pcw_tools_split_across_corridors"] == 0
    assert ms["upgrades"] == {"AEX-D": 1} and gr["upgrades"] == {"AEX-D": 1, "PCWS-C": 1}
    assert s["milp_equals_hungarian_relaxed"] and s["roundtrip_ok"]
    assert s["review_rule_expected_fired"] == s["review_rule_injected"]
    assert {h["hookup"].split("-")[-1] for h in hk if h["governed_by"] == "pressure"} <= {"PCWS", "UPW"}
    assert all(float(x["milp_upgrade_cost"]) < float(x["greedy_upgrade_cost"]) for x in sens), \
        "README says the saving is avoided capacity steps"
    assert float(s10["milp_saving_vs_greedy"]) == s["milp_saving_vs_greedy_reserve10"]
    assert len(exh) == r["exhaust_hookups"]
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [e for e in expected if e not in text]
    for e in missing:
        print("NOT IN README:", repr(e))
    print(f"{len(expected) - len(missing)}/{len(expected)} README figures match results/")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
