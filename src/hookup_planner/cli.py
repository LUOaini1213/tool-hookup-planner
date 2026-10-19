"""Command-line interface: ``python -m hookup_planner <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db as DB
from . import ifc_io, review, scenario
from .capacity import capacity_check, validate_reserve


def _reserve_arg(value: str) -> float:
    try:
        return validate_reserve(float(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _table(rows: list[dict]) -> str:
    if not rows:
        return "(no rows)"
    cols = list(rows[0])
    fmt = lambda v: f"{v:.6g}" if isinstance(v, float) else str(v)
    w = {c: max(len(c), *(len(fmt(r[c])) for r in rows)) for c in cols}
    lines = ["  ".join(c.ljust(w[c]) for c in cols), "  ".join("-" * w[c] for c in cols)]
    lines += ["  ".join(fmt(r[c]).ljust(w[c]) for c in cols) for r in rows]
    return "\n".join(lines)


def cmd_build_db(a) -> int:
    site = scenario.generate(scenario.load_config(a.config))
    ifc = Path(a.ifc)
    ifc.parent.mkdir(parents=True, exist_ok=True)
    ifc_io.write_ifc(site, ifc, title=ifc.name)
    back = ifc_io.read_ifc(ifc)
    dbp = Path(a.db)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    if dbp.exists():
        dbp.unlink()
    conn = DB.connect(dbp)
    DB.write_site(conn, back)
    same = DB.canonical_site(back) == DB.canonical_site(site)
    print(f"IFC written to {ifc}, database populated from it at {dbp}; round trip identical: {same}")
    return 0 if same else 1


def cmd_query(a) -> int:
    conn = DB.connect(a.db)
    if a.what == "headers":
        rows = DB.header_load(conn, a.system)
    elif a.what == "pocs":
        rows = DB.free_pocs(conn, a.system)
    elif a.what == "demand":
        rows = DB.demand_totals(conn)
    else:
        if not a.tool:
            print("--tool is required for 'hookups'", file=sys.stderr)
            return 2
        rows = DB.tool_hookups(conn, a.tool)
    print(_table(rows))
    return 0


def cmd_capacity(a) -> int:
    site = DB.read_site(DB.connect(a.db))
    res = capacity_check(site, a.tools.split(",") if a.tools else None, a.reserve)
    print(_table([{k: s[k] for k in ("system", "unit", "remaining", "new_load", "margin", "status",
                                     "min_upgrade_steps", "min_upgrade_cost")} for s in res["systems"]]))
    return 0


def cmd_review(a) -> int:
    site = DB.read_site(DB.connect(a.db))
    prop = json.loads(Path(a.proposal).read_text(encoding="utf-8"))
    issues = review.review(site, prop["hookups"], prop.get("upgrades", {}), a.reserve)
    print(review.report_md(issues, f"Review of {Path(a.proposal).name}"))
    return 1 if any(i["severity"] == "error" for i in issues) else 0


def cmd_run(a) -> int:
    from .pipeline import run
    s = run(a.out, a.build, a.config, a.rates)
    print(json.dumps({k: s[k] for k in ("hookups_routed", "astar_clashes", "naive_clashes", "milp_objective",
                                         "greedy_objective", "cost_grand_total", "makespan_days")}, indent=2))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="hookup_planner", description="Tool hookup planning on an illustrative "
                                "IFC sub-fab model (synthetic data).")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-db", help="generate the synthetic sub-fab, write IFC, populate SQLite from the IFC")
    b.add_argument("--config", default=None)
    b.add_argument("--ifc", default="build/subfab_base.ifc")
    b.add_argument("--db", default="build/utilities.db")
    b.set_defaults(fn=cmd_build_db)
    q = sub.add_parser("query", help="query the utilities database")
    q.add_argument("what", choices=["headers", "pocs", "demand", "hookups"])
    q.add_argument("--system")
    q.add_argument("--tool")
    q.add_argument("--db", default="build/utilities.db")
    q.set_defaults(fn=cmd_query)
    c = sub.add_parser("capacity", help="header capacity check for the new tools")
    c.add_argument("--db", default="build/utilities.db")
    c.add_argument("--reserve", type=_reserve_arg, default=0.0)
    c.add_argument("--tools", help="comma-separated tool ids (default: all new tools)")
    c.set_defaults(fn=cmd_capacity)
    r = sub.add_parser("review", help="review a hookup proposal JSON against the database")
    r.add_argument("proposal")
    r.add_argument("--db", default="build/utilities.db")
    r.add_argument("--reserve", type=_reserve_arg, default=0.0)
    r.set_defaults(fn=cmd_review)
    a = sub.add_parser("run", help="reproduce results/ end to end")
    a.add_argument("--out", default="results")
    a.add_argument("--build", default="build")
    a.add_argument("--config", default=None)
    a.add_argument("--rates", default=None)
    a.set_defaults(fn=cmd_run)
    args = p.parse_args(argv)
    return args.fn(args)
