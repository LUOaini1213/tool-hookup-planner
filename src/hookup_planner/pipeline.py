"""Reproduce every file in results/ from data/*.json (deterministic, platform independent)."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from . import assign as A
from . import db as DB
from . import engineering as E
from . import ifc_io, review, scenario
from .capacity import capacity_check
from .costing import estimate, take_off
from .numfmt import write_csv, write_json, write_text
from .planner import plan
from .schedule import gantt_png, schedule

RESERVES = (0.0, 0.02, 0.05, 0.1, 0.2)


def pixel_sha256(png_path) -> str:
    """Hash of decoded RGBA pixels (PNG compression bytes may differ between zlib builds)."""
    import matplotlib.image as mpimg
    import numpy as np
    img = (mpimg.imread(str(png_path)) * 255).round().astype(np.uint8)
    return hashlib.sha256(img.tobytes() + str(img.shape).encode()).hexdigest()


def manifest(outdir: Path) -> str:
    lines = []
    for p in sorted(outdir.rglob("*")):
        if not p.is_file() or p.name in ("MANIFEST.sha256", "mutation_report.txt"):
            continue
        rel = p.relative_to(outdir).as_posix()
        if p.suffix == ".png":
            lines.append(f"{pixel_sha256(p)}  {rel} (pixels)")
        else:
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
    return "\n".join(lines) + "\n"


HOOKUP_COLUMNS = ["hookup", "tool", "system", "poc", "header", "corridor", "new_poc", "size", "length_m",
                  "est_length_m", "bends", "flow", "flow_unit", "velocity_mps", "v_max_mps", "tool_side_kpa",
                  "dp_friction_kpa", "dp_fittings_kpa", "dp_static_kpa", "dp_kpa", "available_dp_kpa",
                  "design_current_a", "pressure_ok", "velocity_ok", "valid_model", "governed_by", "regime"]


def hookup_rows(hookups):
    rows = [[h["id"], h["tool"], h["system"], h["poc"], h["header"], h["corridor"], h["new_poc"], h["size"],
             h["length_m"], h["est_length_m"], h["bends"], h["flow"], E.SYSTEMS[h["system"]]["flow_unit"],
             h["velocity"], E.SYSTEMS[h["system"]]["v_max"], h["tool_p_kpa_g"], h["dp_friction_kpa"],
             h["dp_fittings_kpa"], h["dp_static_kpa"], h["dp_total_kpa"], h["available_dp_kpa"],
             h["design_current_a"], h["pressure_ok"], h["velocity_ok"], h["valid_model"], h["governed_by"],
             h["regime"]] for h in hookups]
    return HOOKUP_COLUMNS, rows


def hookup_md(hookups) -> str:
    out = ["# Hookup list", "",
           "ILLUSTRATIVE synthetic data. Pressure loss: Darcy-Weisbach with Swamee-Jain friction factor, fitting "
           "losses (elbows, branch tee, POC valve) and the static term (rho_fluid - rho_air) g dz; see "
           "docs/sources.md. PCWR: available = supply header - supply hookup loss - tool pressure drop - return "
           "header. Power: design current at 400 V three-phase; breaker >= 1.25 x design current.", "",
           "| Hookup | Tool | Utility | POC | Size | Length m | Bends | Velocity m/s | Static kPa | dP kPa | "
           "Available kPa | Governed by | OK |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h in hookups:
        v = "" if h["velocity"] is None else f"{h['velocity']:.2f}"
        st = "" if h["dp_static_kpa"] is None else f"{h['dp_static_kpa']:.3g}"
        dp = "" if h["dp_total_kpa"] is None else f"{h['dp_total_kpa']:.3g}"
        av = "" if h["available_dp_kpa"] is None else f"{h['available_dp_kpa']:.3g}"
        if h["design_current_a"] is not None:
            dp = f"{h['design_current_a']:.0f} A design"
        ok = "yes" if (h["pressure_ok"] and h["velocity_ok"] and h["valid_model"]) else "NO"
        poc = h["poc"] + (" (new)" if h["new_poc"] else "")
        out.append(f"| {h['id']} | {h['tool']} | {h['system']} | {poc} | {h['size']} | {h['length_m']:.1f} | "
                   f"{h['bends']} | {v} | {st} | {dp} | {av} | {h['governed_by']} | {ok} |")
    return "\n".join(out) + "\n"


def demo_proposal(site, proposal, upgrades, seed=11):
    """One fault of each rule-targeted kind on distinct hookups, for the sample review report."""
    rng = random.Random(seed)
    prop, ups, notes = [dict(h) for h in proposal], dict(upgrades), []
    used = set()
    for fault in review.RULE_FAULTS:
        for t in range(len(prop)):
            if prop[t]["id"] in used:
                continue
            inj = review.inject(site, prop, ups, fault, t, rng)
            if inj is None:
                continue
            prop, ups, ids = inj
            used.update(ids)
            notes.append({"fault": fault, "hookups": ids})
            break
    return prop, ups, notes


def split_pcw_tools(site_w, reqs, assignment, newpocs) -> int:
    """Tools whose PCW supply and return are assigned to different corridors."""
    n = 0
    for s, t in A.pcw_pairs(reqs):
        if s in assignment and t in assignment and \
                A.corridor(site_w, newpocs, assignment[s]) != A.corridor(site_w, newpocs, assignment[t]):
            n += 1
    return n


def run(outdir="results", build="build", cfg_path=None, rates_path=None) -> dict:
    out, bld = Path(outdir), Path(build)
    out.mkdir(parents=True, exist_ok=True)
    bld.mkdir(parents=True, exist_ok=True)
    cfg = scenario.load_config(cfg_path)
    rates = scenario.load_rates(rates_path)

    # 1. synthetic model -> IFC -> database (round trip)
    seed_site = scenario.generate(cfg, rates)
    ifc_io.write_ifc(seed_site, out / "subfab_base.ifc", title="subfab_base.ifc")
    from_ifc = ifc_io.read_ifc(out / "subfab_base.ifc")
    dbfile = bld / "utilities.db"
    if dbfile.exists():
        dbfile.unlink()
    conn = DB.connect(dbfile)
    DB.write_site(conn, from_ifc)
    site = DB.read_site(conn)
    rt = {"ifc_equals_seed": DB.canonical_site(from_ifc) == DB.canonical_site(seed_site),
          "db_equals_seed": DB.canonical_site(site) == DB.canonical_site(seed_site),
          "counts": {k: len(seed_site[k]) for k in ("systems", "columns", "headers", "pocs", "equipment", "tools",
                                                     "demands", "hookups")},
          "ports_base": ifc_io.port_connectivity(out / "subfab_base.ifc")}
    write_json(out / "roundtrip.json", rt)

    # 2. plan
    P = plan(site, rates)
    cap = P["capacity"]
    write_json(out / "capacity_check.json", cap)
    write_csv(out / "capacity_check.csv",
              ["system", "unit", "usable", "connected_load", "remaining", "new_load", "margin", "utilisation_after",
               "status", "min_upgrade_steps", "min_upgrade_cost", "new_connections", "free_pocs"],
              [[s["system"], s["unit"], s["usable"], s["connected_load"], s["remaining"], s["new_load"], s["margin"],
                s["utilisation_after"], s["status"], s["min_upgrade_steps"], s["min_upgrade_cost"],
                s["new_connections"], s["free_pocs"]] for s in cap["systems"]])

    reqs = P["requirements"]
    sens = []
    for reserve in RESERVES:
        c = capacity_check(site, None, reserve)
        m = A.solve(P["site"], reqs, P["candidates"], P["new_poc_specs"], rates, reserve)
        g = A.greedy(P["site"], reqs, P["candidates"], P["new_poc_specs"], rates, reserve)
        sens.append([reserve, sum(1 for s in c["systems"] if s["status"] == "SHORTFALL"),
                     sum(m["upgrades"].values()), m["upgrade_cost"], len(m["new_pocs"]), m["est_hookup_cost"],
                     m["objective"], sum(g["upgrades"].values()), g["upgrade_cost"], g["est_hookup_cost"],
                     g["objective"], 1 - m["objective"] / g["objective"], len(m["unassigned"]), len(g["unassigned"])])
    write_csv(out / "capacity_sensitivity.csv",
              ["reserve", "systems_short", "milp_upgrade_steps", "milp_upgrade_cost", "milp_new_pocs",
               "milp_hookup_cost", "milp_objective", "greedy_upgrade_steps", "greedy_upgrade_cost",
               "greedy_hookup_cost", "greedy_objective", "milp_saving_vs_greedy", "milp_unassigned",
               "greedy_unassigned"], sens)

    asg = {k: {kk: v[kk] for kk in ("objective", "est_length_m", "est_hookup_cost", "upgrade_cost", "upgrades")}
           | {"new_pocs": len(v["new_pocs"]), "unassigned": len(v["unassigned"]),
              "unassigned_systems": sorted({reqs[r]["system"] for r in v["unassigned"]}),
              "pcw_tools_split_across_corridors": split_pcw_tools(P["site"], reqs, v["assign"], P["new_poc_specs"])}
           for k, v in P["assignment"].items()}
    asg["pcw_tools"] = len(A.pcw_pairs(reqs))
    write_json(out / "assignment.json", asg)
    rows = []
    for r, d in enumerate(reqs):
        row = [d["tool"], d["system"], d["flow"]]
        for k in ("milp", "greedy"):
            key = P["assignment"][k]["assign"].get(r)
            row += [A.position(key) if key else "", P["candidates"][r].get(key, "") if key else "",
                    A.corridor(P["site"], P["new_poc_specs"], key) if key else ""]
        rows.append(row)
    write_csv(out / "assignment.csv", ["tool", "system", "flow", "milp_poc", "milp_est_length_m", "milp_corridor",
                                       "greedy_poc", "greedy_est_length_m", "greedy_corridor"], rows)

    hk = P["hookups"]
    DB.write_plan(conn, P["site"], hk)
    DB.dump_tables(conn, out / "db")
    write_json(out / "proposal.json", {"upgrades": P["assignment"]["milp"]["upgrades"],
                                       "hookups": [{k: h[k] for k in ("id", "tool", "system", "poc", "size", "points")}
                                                   for h in hk]})
    hdr, rows = hookup_rows(hk)
    write_csv(out / "hookup_list.csv", hdr, rows)
    write_text(out / "hookup_list.md", hookup_md(hk))
    gov: dict = {}
    for h in hk:
        gov[h["governed_by"]] = gov.get(h["governed_by"], 0) + 1
    naive_kinds: dict = {}
    for c in P["naive_clashes"]:
        naive_kinds[c["b_kind"]] = naive_kinds.get(c["b_kind"], 0) + 1
    routed = sum(h["length_m"] for h in hk)
    exh = [h for h in hk if E.SYSTEMS[h["system"]]["kind"] == "exhaust"]
    rsum = {"hookups": len(hk), "requirements": len(reqs), "failures": P["failures"], "reassigned": P["reassigned"],
            "routed_length_m": routed, "manhattan_lower_bound_m": P["lower_bound_length_m"],
            "routed_over_lower_bound": routed / P["lower_bound_length_m"], "bends": sum(h["bends"] for h in hk),
            "astar_clashes": len(P["clashes"]), "naive_clashes": len(P["naive_clashes"]),
            "naive_clashes_by_kind": naive_kinds,
            "naive_hookups_with_clash": len({c["a"].split("#")[0] for c in P["naive_clashes"]}),
            "sizes_governed_by": gov,
            "exhaust_hookups": len(exh),
            "exhaust_below_1000_fpm": sum(1 for h in exh if h["velocity"] < E.EXHAUST_RANGE_V[0]),
            "exhaust_dp_range_kpa": [min(h["dp_total_kpa"] for h in exh), max(h["dp_total_kpa"] for h in exh)],
            "exhaust_static_abs_max_kpa": max(abs(h["dp_static_kpa"]) for h in exh),
            "negative_dp_exhaust_hookups": sum(1 for h in exh if h["dp_total_kpa"] < 0),
            "pcwr_min_margin_kpa": min(h["available_dp_kpa"] - h["dp_total_kpa"] for h in hk
                                       if h["system"] == E.PCW_PAIR[1]),
            "pcw_tools_split_across_corridors": sum(
                1 for t in {h["tool"] for h in hk if h["system"] == E.PCW_PAIR[1]}
                if len({h["corridor"] for h in hk if h["tool"] == t and h["system"] in E.PCW_PAIR}) > 1),
            "all_checks_pass": all(h["pressure_ok"] and h["velocity_ok"] and h["valid_model"] for h in hk)}
    write_json(out / "routing_summary.json", rsum)
    write_csv(out / "clashes_naive.csv", ["run", "other", "other_kind", "type", "gap_m"],
              [[c["a"], c["b"], c["b_kind"], c["type"], c["gap_m"]] for c in P["naive_clashes"]])
    write_csv(out / "clashes_astar.csv", ["run", "other", "other_kind", "type", "gap_m"],
              [[c["a"], c["b"], c["b_kind"], c["type"], c["gap_m"]] for c in P["clashes"]])

    # 3. take-off, cost, schedule
    mto = take_off(hk)
    write_csv(out / "mto.csv", ["category", "system", "material", "size", "length_m", "elbows", "hookups"],
              [[m["category"], m["system"], m["material"], m["size"], m["length_m"], m["elbows"], m["hookups"]]
               for m in mto])
    upgrades = P["assignment"]["milp"]["upgrades"]
    cost = estimate(rates, hk, upgrades, P["site"])
    write_csv(out / "cost_estimate.csv", ["hookup", "tool", "system", "material", "fittings", "labour_h", "labour",
                                          "tie_in", "test", "total"],
              [[c[k] for k in ("hookup", "tool", "system", "material", "fittings", "labour_h", "labour", "tie_in",
                               "test", "total")] for c in cost["per_hookup"]])
    write_json(out / "cost_summary.json", {k: v for k, v in cost.items() if k != "per_hookup"})
    sch = schedule(rates, hk, upgrades, P["site"])
    write_csv(out / "schedule.csv", ["id", "tool", "type", "resource", "start_day", "finish_day", "duration_days",
                                     "preds"], [[t[k] for k in ("id", "tool", "type", "resource", "start_day",
                                                                "finish_day", "duration_days", "preds")]
                                                for t in sch["tasks"]])
    write_json(out / "schedule_summary.json", {k: v for k, v in sch.items() if k != "tasks"} | {"tasks": len(sch["tasks"])})
    gantt_png(sch, out / "gantt.png")

    # 4. IFC with the planned routes
    ifc_io.write_ifc(P["site"], out / "subfab_with_hookups.ifc", new_hookups=hk, title="subfab_with_hookups.ifc")
    ports_planned = ifc_io.port_connectivity(out / "subfab_with_hookups.ifc")

    # 5. drawing review aid
    proposal = [{k: h[k] for k in ("id", "tool", "system", "poc", "size", "points")} for h in hk]
    clean = review.review(P["site"], proposal, upgrades)
    write_text(out / "review_clean.md", review.report_md(clean, "Review of the planner's proposal"))
    demo, demo_up, notes = demo_proposal(P["site"], proposal, upgrades)
    demo_issues = review.review(P["site"], demo, demo_up)
    md = review.report_md(demo_issues, "Review of a sample proposal with seeded errors")
    md += "\n## Seeded errors\n\n" + "\n".join(f"- {n['fault']}: {', '.join(n['hookups'])}" for n in notes) + "\n"
    write_text(out / "review_demo.md", md)
    ev = review.evaluate_faults(P["site"], proposal, upgrades)
    write_json(out / "review_eval.json", ev)
    write_text(out / "review_eval.md", review_eval_md(ev))

    # 6. headline summary
    ms = P["assignment"]["milp"]
    gr = P["assignment"]["greedy"]
    sens10 = next(s for s in sens if s[0] == 0.1)
    rf, of = ev["rule_faults"].values(), ev["open_faults"].values()
    summary = {
        "notice": scenario.NOTICE,
        "tools_new": len({d["tool"] for d in reqs}), "tools_existing": sum(1 for t in site["tools"] if t["status"] == "existing"),
        "requirements": len(reqs), "hookups_routed": len(hk),
        "systems_short": [s["system"] for s in cap["systems"] if s["status"] == "SHORTFALL"],
        "milp_objective": ms["objective"], "greedy_objective": gr["objective"],
        "milp_saving_vs_greedy_reserve0": 1 - ms["objective"] / gr["objective"],
        "milp_saving_vs_greedy_reserve10": sens10[11],
        "milp_saving_vs_greedy_range": [min(s[11] for s in sens), max(s[11] for s in sens)],
        "milp_upgrades": ms["upgrades"], "greedy_upgrades": gr["upgrades"], "milp_new_pocs": len(ms["new_pocs"]),
        "milp_equals_hungarian_relaxed": abs(P["assignment"]["milp_relaxed"]["objective"]
                                             - P["assignment"]["hungarian_relaxed"]["objective"]) < 1e-6,
        "routed_length_m": routed, "routed_over_lower_bound": rsum["routed_over_lower_bound"],
        "astar_clashes": rsum["astar_clashes"], "naive_clashes": rsum["naive_clashes"],
        "pressure_governed_sizes": gov.get("pressure", 0),
        "cost_grand_total": cost["grand_total"], "cost_hookups": cost["hookup_total"],
        "cost_pls": cost["pls_total"], "currency": cost["currency"],
        "last_utilities_on_day": sch["last_utilities_on_day"], "makespan_days": sch["makespan_days"],
        "ifc_port_mismatches": len(rt["ports_base"]["mismatches"]) + len(ports_planned["mismatches"]),
        "ifc_ports_planned": ports_planned["ports"], "ifc_port_connections_planned": ports_planned["port_connections"],
        "review_clean_issues": len(clean),
        "review_rule_injected": sum(f["injected"] for f in rf),
        "review_rule_expected_fired": sum(f["expected_fired"] for f in rf),
        "review_rule_unexplained_elsewhere": sum(f["unexplained_elsewhere"] for f in rf),
        "review_open_injected": sum(f["injected"] for f in of),
        "review_open_caught": sum(f["caught"] for f in of),
        "roundtrip_ok": rt["ifc_equals_seed"] and rt["db_equals_seed"],
    }
    write_json(out / "summary.json", summary)
    conn.close()
    write_text(out / "MANIFEST.sha256", manifest(out))
    return summary


def review_eval_md(ev: dict) -> str:
    def codes(c):
        return ", ".join(f"{k} {v}" for k, v in c.items()) or "-"
    out = ["# Review aid: fault-injection results", "",
           "ILLUSTRATIVE synthetic data. One fault at a time is injected into the planner's own (clean) proposal.", "",
           "## Check-coverage test (faults constructed to violate each rule)", "",
           "Each fault below was written to break one specific rule, so detection is expected by construction; the "
           "table only shows that each check is wired up. Findings elsewhere are *explained* when they follow "
           "mechanically from the fault (clash with the faulted run, load of a header the fault changed, PCW "
           "partner of a faulted hookup).", "",
           "| Fault | Cases | Expected rule fired | All findings on the faulted hookups (count) | "
           "Explained elsewhere | Unexplained elsewhere |", "|---|---|---|---|---|---|"]
    for name, f in ev["rule_faults"].items():
        out.append(f"| {name} | {f['injected']} | {f['expected_fired']} | {codes(f['codes_on_target'])} | "
                   f"{f['explained_elsewhere']} | {f['unexplained_elsewhere']} |")
    out += ["", "## Faults not targeted by any rule", "",
            "Written after the checks, with no rule aimed at them. A case is caught if any finding lands on a "
            "faulted hookup.", "",
            "| Fault | Cases | Caught | Findings on the faulted hookups (count) | Explained elsewhere | "
            "Unexplained elsewhere |", "|---|---|---|---|---|---|"]
    for name, f in ev["open_faults"].items():
        out.append(f"| {name} | {f['injected']} | {f['caught']} | {codes(f['codes_on_target'])} | "
                   f"{f['explained_elsewhere']} | {f['unexplained_elsewhere']} |")
    return "\n".join(out) + "\n"
