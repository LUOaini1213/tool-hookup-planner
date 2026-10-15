"""Mutation check: each deliberate bug must make at least one unit test fail.

The repository is copied to a temporary directory and every mutant is applied there, so
the working tree is never modified.  Writes results/mutation_report.txt.
Run from anywhere:  python tests/mutate.py [--jobs N]   (the report does not depend on N)
"""
from __future__ import annotations

import argparse
import queue
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = "src/hookup_planner/"

MUTANTS = [
    # hydraulics
    (P + "hydraulics.py", "    if re < E.RE_LAMINAR_MAX:\n        return 64.0 / re", "    if re < 0:\n        return 64.0 / re"),
    (P + "hydraulics.py", "return 64.0 / re", "return 32.0 / re"),
    (P + "hydraulics.py", "5.74 / re ** 0.9", "5.74 / re ** 0.8"),
    (P + "hydraulics.py", "rel_rough / 3.7", "rel_rough / 3.2"),
    (P + "hydraulics.py", "return flow / 60000.0", "return flow / 6000.0"),
    (P + "hydraulics.py", "* (E.T_OP_K / E.T_STD_K)", "* (E.T_STD_K / E.T_OP_K)"),
    (P + "hydraulics.py", "/ (E.R_GAS * E.T_OP_K)", "/ (E.R_GAS * E.T_STD_K)"),
    (P + "hydraulics.py", "(n_elbows * E.ELBOW_K + k_fit) * dyn", "(n_elbows + k_fit) * dyn"),
    (P + "hydraulics.py", "(rho - E.RHO_AIR_AMBIENT) * E.G * dz_flow / 1000.0",
     "(rho - E.RHO_AIR_AMBIENT) * E.G * abs(dz_flow) / 1000.0"),
    (P + "hydraulics.py", "return header_p_kpa_g - tool_p_kpa_g", "return header_p_kpa_g + tool_p_kpa_g"),
    (P + "hydraulics.py", "return tool_p_kpa_g - header_p_kpa_g", "return header_p_kpa_g - tool_p_kpa_g"),
    (P + "hydraulics.py", 'v_ok = loss["velocity"] <= sysd["v_max"]', 'v_ok = loss["velocity"] <= 1.2 * sysd["v_max"]'),
    (P + "hydraulics.py", 'valid = abs(loss["dp_total_kpa"]) < E.GAS_DP_FRACTION_MAX * abs_pressure_kpa(header_p_kpa_g)',
     "valid = True"),
    (P + "hydraulics.py", 'elif vel_only is not None and s["label"] == vel_only["label"]:', "elif False:"),
    # new: buoyancy, fittings, PCW loop, breaker rule, governing label
    (P + "hydraulics.py", "dp_static = (rho - E.RHO_AIR_AMBIENT) * E.G", "dp_static = rho * E.G"),
    (P + "hydraulics.py", "(n_elbows * E.ELBOW_K + k_fit) * dyn", "(n_elbows * E.ELBOW_K) * dyn"),
    (P + "hydraulics.py", "return supply_header_p - supply_dp - tool_dp", "return supply_header_p - tool_dp"),
    (P + "hydraulics.py", 'ok = E.breaker_ok(size["amps"], flow)', 'ok = size["amps"] >= flow'),
    (P + "hydraulics.py", 'governed = "pressure" if not below["pressure_ok"] else "gas validity"',
     'governed = "pressure"'),
    # engineering constants
    (P + "engineering.py", "ELBOW_K = 0.3 ", "ELBOW_K = 0.2 "),
    (P + "engineering.py", "0.3048 / 60.0", "0.3048 / 50.0"),
    (P + "engineering.py", '"id": (od - 2 * wall) / 1000.0', '"id": (od - wall) / 1000.0'),
    (P + "engineering.py", "RHO_AIR_AMBIENT = P_ATM_KPA * 1000.0 * M_AIR / (R_GAS * T_OP_K)",
     "RHO_AIR_AMBIENT = P_ATM_KPA * 1000.0 * M_AIR / (R_GAS * T_STD_K)"),
    (P + "engineering.py", '"liquid": TEE_BRANCH_K + BALL_VALVE_K', '"liquid": TEE_BRANCH_K'),
    (P + "engineering.py", "(T_OP_K - 280.0) / 20.0", "(T_OP_K - 273.15) / 20.0"),
    (P + "engineering.py", '"id": (od - 2 * wall) * INCH_M', '"id": (od - wall) * INCH_M'),
    (P + "engineering.py", '"ss_ep_tube": 0.0008e-3', '"ss_ep_tube": 0.006e-3'),
    (P + "engineering.py", "return kva * 1000.0 / (math.sqrt(3.0) * V_LL)", "return kva * 1000.0 / (3.0 * V_LL)"),
    (P + "engineering.py", "return amps >= CONTINUOUS_LOAD_FACTOR * kva_to_amps(kva) - 1e-9",
     "return amps >= kva_to_amps(kva) - 1e-9"),
    (P + "engineering.py", "return amps / CONTINUOUS_LOAD_FACTOR * math.sqrt(3.0) * V_LL / 1000.0",
     "return amps * math.sqrt(3.0) * V_LL / 1000.0"),
    # geometry
    (P + "geometry.py", "max(0.0, lo2[a] - hi1[a], lo1[a] - hi2[a])", "max(0.0, lo2[a] - hi1[a])"),
    (P + "geometry.py", "return box_gap(a.lo, a.hi, b.lo, b.hi) - a.r - b.r", "return box_gap(a.lo, a.hi, b.lo, b.hi) - a.r"),
    (P + "geometry.py", '"type": "hard" if g < -EPS else "clearance"', '"type": "hard" if g < clearance else "clearance"'),
    (P + "geometry.py", 'if b.kind == "route" and b.owner == a.owner:', "if False:"),
    (P + "geometry.py", "if h >= n_exist and h - n_exist <= idx:", "if h >= n_exist and h - n_exist < idx:"),
    (P + "geometry.py", "            if h >= n_exist and h - n_exist <= idx:\n                continue",
     "            if False:\n                continue"),
    # lattice / A*
    (P + "lattice.py", "(BEND_COST if nd != d else 0)", "(BEND_COST if nd == d else 0)"),
    (P + "lattice.py", "if m == goal and nd != UP:", "if False:"),
    (P + "lattice.py", "g2 + STEP_COST * self.manhattan(m, goal)", "g2 + 3 * STEP_COST * self.manhattan(m, goal)"),
    (P + "lattice.py", "ok = ((f >= r + clearance - EPS)", "ok = ((f >= r - EPS)"),
    (P + "lattice.py", "(f > EPS) & ", ""),
    (P + "lattice.py", "            if full[cur] >= need:\n                return nodes",
     "            if wo[cur] >= need:\n                return nodes"),
    (P + "lattice.py", "for depth in range(PEN_DEPTH + 1):", "for depth in range(1):"),
    (P + "lattice.py", "if _unit(d1) != _unit(d2):", "if d1 != d2:"),
    # assignment
    (P + "assign.py", 'A[hrow[_header_of(site, newpocs, p)], n] = d["flow"] * E.COINCIDENCE_FACTOR[d["system"]]',
     "A[hrow[_header_of(site, newpocs, p)], n] = 0.0"),
    (P + "assign.py", 'A[hrow[h], nx_ + n] = -idx.headers[h]["upgrade_step"]',
     'A[hrow[h], nx_ + n] = -2 * idx.headers[h]["upgrade_step"]'),
    (P + "assign.py", 'return c + (rates["new_poc_each"] if "@" in p else 0.0)', "return c"),
    (P + "assign.py", "A[prow[position(p)], n] = 1.0", "A[prow[position(p)], n] = 0.0"),
    (P + "assign.py", "while rem[h] < load:", "if rem[h] < load:"),
    (P + "assign.py", 'and p["id"] not in used and p["rated_flow"] >= d["flow"]]', 'and p["id"] not in used]'),
    (P + "assign.py", 'h["capacity"] * (1.0 - reserve) - loads[h["id"]]', 'h["capacity"] - loads[h["id"]]'),
    # new: PCW pairing
    (P + "assign.py", "    if pairing:\n        for s, t in pcw_pairs(reqs):", "    if False:\n        for s, t in pcw_pairs(reqs):"),
    (P + "assign.py", "A[row0 + k, n] = -1.0", "A[row0 + k, n] = 1.0"),
    (P + "assign.py", "lb[row0 + k] = ub[row0 + k] = 0.0", "ub[row0 + k] = 0.0"),
    (P + "assign.py", "            opts = [o for o in opts if corridor(site, newpocs, o[1]) == want]",
     "            opts = opts"),
    # capacity / model
    (P + "capacity.py", "steps = math.ceil(shortfall / step - 1e-9) if shortfall > 0 else 0",
     "steps = math.floor(shortfall / step) if shortfall > 0 else 0"),
    (P + "capacity.py", 'usable = h["capacity"] * (1.0 - reserve)', 'usable = h["capacity"]'),
    (P + "model.py", 'if hk["status"] not in ("released", "installed", "tested"):',
     'if hk["status"] not in ("released", "installed", "tested", "planned"):'),
    (P + "model.py", "return E.FAB_FLOOR_Z - poc_z", "return poc_z - E.FAB_FLOOR_Z"),
    (P + "model.py", 'if E.size_index(system, sel["size"]["label"]) <= E.size_index(system, size["label"]):',
     "if True:"),
    (P + "model.py", "    if system != E.PCW_PAIR[1]:\n        return p_req", "    if True:\n        return p_req"),
    (P + "schema.sql", "WHEN k.status IN ('installed', 'tested', 'released')\n                         THEN",
     "WHEN k.status IN ('installed', 'tested', 'released', 'planned')\n                         THEN"),
    # planner (new: supply loss handed to the return)
    (P + "planner.py", 'supply[d["tool"]] = (hdr["pressure_kpa_g"], ev["dp_total_kpa"], hdr["corridor"])',
     'supply[d["tool"]] = (hdr["pressure_kpa_g"], 0.0, hdr["corridor"])'),
    # review
    (P + "review.py", 'if d["flow"] > poc["rated_flow"] + EPS:', 'if d["flow"] > 2 * poc["rated_flow"] + EPS:'),
    (P + "review.py", 'start_ok = _close(pts[0], (poc["x"], poc["y"], poc["z"]))', "start_ok = True"),
    (P + "review.py", '+ upgrades.get(h, 0) * hdr["upgrade_step"]', '+ (upgrades.get(h, 0) + 1) * hdr["upgrade_step"]'),
    (P + "review.py", "if len(users) > 1:", "if len(users) > 2:"),
    (P + "review.py", 'if poc["system"] != hk["system"]:\n            add("WRONG_UTILITY"',
     'if False:\n            add("WRONG_UTILITY"'),
    # new: review PCW rules, open faults, classification
    (P + "review.py", 'key=lambda n: (proposal[n]["system"] == E.PCW_PAIR[1], n)', "key=lambda n: n"),
    (P + "review.py", 'supply[hk["tool"]] = (idx.headers[poc["header"]]["pressure_kpa_g"], ev["dp_total_kpa"])',
     'supply[hk["tool"]] = (idx.headers[poc["header"]]["pressure_kpa_g"], 0.0)'),
    (P + "review.py", "if s and r and s[0] != r[0]:", "if False:"),
    (P + "review.py", 'tool_p = float("inf")', "tool_p = 0.0"),
    (P + "review.py", "(px, q[1], q[2]), (px, py, q[2]),", "(px, py, q[2]),"),
    (P + "review.py", "wrong = d[\"flow\"] * 1000.0 / 60.0", "wrong = d[\"flow\"]"),
    (P + "review.py", "wrong = d[\"flow\"] * 60.0 / 1000.0", "wrong = d[\"flow\"] * 1000.0 / 60.0"),
    (P + "review.py", "dz_flow(hk[\"system\"], idx.pocs[hk[\"poc\"]][\"z\"]), hp)[\"dp_total_kpa\"] >= limit]",
     "dz_flow(hk[\"system\"], idx.pocs[hk[\"poc\"]][\"z\"]), hp)[\"dp_total_kpa\"] < limit]"),
    (P + "review.py", 'partner["points"] = _redirect_end(partner["points"], ds["px"], ds["py"])', "pass"),
    (P + "review.py", 'if s == hk["system"] and t != hk["tool"]', 'if s == hk["system"] and t == hk["tool"]'),
    (P + "review.py", '                or (i["hookup"] in partners and i["code"]',
     '                or (False and i["code"]'),
    # schedule / costing
    (P + "schedule.py", "if all(u[s] < crews[res] for s in range(start, need)):",
     "if all(u[s] <= crews[res] for s in range(start, need)):"),
    (P + "schedule.py", 'start = max([done[p] for p in t["preds"]], default=0)', "start = 0"),
    (P + "schedule.py", "max(1, math.ceil(days * 2 - 1e-9))", "max(1, round(days * 2))"),
    (P + "schedule.py", "\"preds\": [f\"HU-{hk['id']}\", f\"MS-{hk['tool']}\"]", "\"preds\": [f\"HU-{hk['id']}\"]"),
    (P + "schedule.py", "\"preds\": [f\"UO-{tool}\"]", "\"preds\": []"),
    (P + "costing.py", 'return r["a"] + r["b"] * s["od"] * 1000.0', 'return r["a"] + r["b"] * s["od"]'),
    (P + "costing.py", 'elbows = hk["bends"] if kind != "power" else 0', 'elbows = hk["bends"]'),
    # IFC / planner / formatting
    (P + "ifc_io.py", '"x1": r10(x + s.Directrix.Points[-1].Coordinates[0])',
     '"x1": r10(s.Directrix.Points[-1].Coordinates[0])'),
    (P + "ifc_io.py", "w.placement((cx, cy, 0.0), fab_pl)", "w.placement((cx, cy, 0.0), sub_pl)"),
    (P + "ifc_io.py", "        w.connect(hp, pin, f\"hdr-poc/{p['id']}\")", "        pass"),
    (P + "ifc_io.py", 'VIEW_DEFINITION = "ViewDefinition [ReferenceView_V1.2]"',
     'VIEW_DEFINITION = "ViewDefinition [CoordinationView]"'),
    (P + "planner.py", 'return b.kind == "header" and a.eid.endswith("#0") and poc_header.get(a.meta.get("poc")) == b.eid',
     'return b.kind == "header" and poc_header.get(a.meta.get("poc")) == b.eid'),
    (P + "planner.py", "            lat.reserved[n] = True", "            pass"),
    (P + "numfmt.py", 'v = float(f"{x:.10g}")', 'v = float(f"{x:.12g}")'),
]

# Mutants found to be equivalent (no observable behaviour change on any input the code can
# receive) are listed here with the reason, and are not counted as escapes.  The key is
# "<file>: <first line of the original> -> <first line of the replacement>".
EQUIVALENT: dict[str, str] = {
    "geometry.py: if h >= n_exist and h - n_exist <= idx: -> if h >= n_exist and h - n_exist < idx:":
        "the only extra pair it admits is a run tested against itself, which the same-owner rule skips",
}


def key(rel: str, old: str, new: str) -> str:
    first = lambda s: s.strip().splitlines()[0] if s.strip() else "(removed)"
    return f"{rel.split('/')[-1]}: {first(old)} -> {first(new)}"


def run_tests(cwd: Path) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"],
                          cwd=cwd, capture_output=True, text=True).returncode


def copy_repo(dst: Path) -> Path:
    for part in ("src", "tests", "data"):
        shutil.copytree(ROOT / part, dst / part, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "pyproject.toml", dst / "pyproject.toml")
    return dst


def run_mutant(work: Path, n: int, rel: str, old: str, new: str) -> int:
    f = work / rel
    text = f.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation target not unique in {rel}: {old[:60]!r}"
    f.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    try:
        if rel.endswith(".py"):
            comp = subprocess.run([sys.executable, "-m", "py_compile", str(f)], capture_output=True)
            assert comp.returncode == 0, f"mutant {n} does not compile"
        return run_tests(work)
    finally:
        f.write_text(text, encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=1, help="parallel workers, each on its own copy (default 1)")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as td:
        works: queue.Queue = queue.Queue()
        for j in range(max(1, args.jobs)):
            works.put(copy_repo(Path(td) / f"repo{j}"))
        first = works.get()
        assert run_tests(first) == 0, "tests fail on the unmutated code; fix them first"
        col = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
                              "tests"], cwd=first, capture_output=True, text=True).stdout
        works.put(first)
        n_tests = sum(1 for line in col.splitlines() if "::" in line)

        def job(item):
            n, (rel, old, new) = item
            w = works.get()
            try:
                return run_mutant(w, n, rel, old, new)
            finally:
                works.put(w)

        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            rcs = list(ex.map(job, enumerate(MUTANTS, 1)))
    lines, killed, equiv = [], 0, 0
    for n, ((rel, old, new), rc) in enumerate(zip(MUTANTS, rcs), 1):
        label = f"M{n:02d} {rel.split('/')[-1]}: {old.strip().splitlines()[0][:70]}"
        if rc != 0:
            killed += 1
            status = "killed "
        elif key(rel, old, new) in EQUIVALENT:
            equiv += 1
            status = "equiv. "
        else:
            status = "ESCAPED"
        lines.append(f"{status}  {label}")
        print(lines[-1], flush=True)
    total = len(MUTANTS)
    summary = f"{killed}/{total} mutants killed ({equiv} documented equivalent, {total - killed - equiv} escaped)"
    print(summary)
    out = ROOT / "results" / "mutation_report.txt"
    eq = "".join(f"  {k}\n    -> {v}\n" for k, v in EQUIVALENT.items())
    out.write_text(f"Mutation check (tests/mutate.py) against {n_tests} unit tests\n\n" + "\n".join(lines)
                   + "\n\nEquivalent mutants:\n" + eq + "\n" + summary + "\n", encoding="utf-8", newline="\n")
    return 0 if killed + equiv == total else 1


if __name__ == "__main__":
    sys.exit(main())
