"""SQLite utilities database: schema, load/read a site, canonical dumps and queries."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .numfmt import canon, write_csv

SCHEMA = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")

TABLES = {
    # table: (site key, columns, order by)
    "utility_system": ("systems", ["code", "name", "kind", "role", "fluid", "flow_unit", "material", "v_max",
                                   "coincidence_factor"], "code"),
    "structural_column": ("columns", ["id", "x", "y", "w", "d", "z0", "z1"], "id"),
    "header": ("headers", ["id", "system", "corridor", "y", "z", "x0", "x1", "od", "capacity", "pressure_kpa_g",
                           "upgrade_step", "upgrade_cost", "upgrade_days"], "id"),
    "poc": ("pocs", ["id", "header", "system", "x", "y", "z", "size", "rated_flow", "status"], "id"),
    "equipment": ("equipment", ["id", "x0", "y0", "z0", "x1", "y1", "z1"], "id"),
    "tool": ("tools", ["id", "category", "status", "x0", "y0", "x1", "y1", "height"], "id"),
    "tool_demand": ("demands", ["tool", "system", "flow", "p_req", "px", "py"], "tool, system"),
    "hookup": ("hookups", ["id", "tool", "system", "poc", "status", "size"], "id"),
}


def connect(path=":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def write_site(conn: sqlite3.Connection, site: dict) -> None:
    with conn:
        for k, v in sorted(site["meta"].items()):
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (k, json.dumps(v)))
        for table, (key, cols, _) in TABLES.items():
            q = f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            conn.executemany(q, [tuple(row[c] for c in cols) for row in site[key]])
        for hk in site["hookups"]:
            conn.executemany("INSERT INTO route_point(hookup, seq, x, y, z) VALUES (?, ?, ?, ?, ?)",
                             [(hk["id"], n, p[0], p[1], p[2]) for n, p in enumerate(hk["points"])])


def write_plan(conn: sqlite3.Connection, site_w: dict, hookups: list[dict]) -> None:
    """Store planned (new) POCs and planned hookups with their routes."""
    cols = TABLES["poc"][1]
    with conn:
        conn.executemany(f"INSERT INTO poc({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [tuple(p[c] for c in cols) for p in site_w["pocs"] if p["status"] == "planned"])
        conn.executemany("INSERT INTO hookup(id, tool, system, poc, status, size) VALUES (?, ?, ?, ?, 'planned', ?)",
                         [(h["id"], h["tool"], h["system"], h["poc"], h["size"]) for h in hookups])
        for h in hookups:
            conn.executemany("INSERT INTO route_point(hookup, seq, x, y, z) VALUES (?, ?, ?, ?, ?)",
                             [(h["id"], n, p[0], p[1], p[2]) for n, p in enumerate(h["points"])])


def read_site(conn: sqlite3.Connection) -> dict:
    site = {"meta": {k: json.loads(v) for k, v in conn.execute("SELECT key, value FROM meta ORDER BY key")}}
    for table, (key, cols, order) in TABLES.items():
        rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}").fetchall()
        site[key] = [dict(zip(cols, r)) for r in rows]
    pts: dict[str, list] = {}
    for hid, x, y, z in conn.execute("SELECT hookup, x, y, z FROM route_point ORDER BY hookup, seq"):
        pts.setdefault(hid, []).append([x, y, z])
    for hk in site["hookups"]:
        hk["points"] = pts.get(hk["id"], [])
    return site


def canonical_site(site: dict) -> dict:
    """Order-independent, rounded copy used for equality checks and dumps."""
    out = {"meta": canon(site["meta"])}
    for _, (key, cols, order) in TABLES.items():
        keys = [c.strip() for c in order.split(",")]
        rows = [canon(dict(r)) for r in site[key]]
        out[key] = sorted(rows, key=lambda r: tuple(r[k] for k in keys))
    return out


def dump_tables(conn: sqlite3.Connection, outdir) -> list[str]:
    outdir = Path(outdir)
    files = []
    for table, (_, cols, order) in TABLES.items():
        rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}").fetchall()
        write_csv(outdir / f"{table}.csv", cols, [list(r) for r in rows])
        files.append(f"{table}.csv")
    rows = conn.execute("SELECT hookup, seq, x, y, z FROM route_point ORDER BY hookup, seq").fetchall()
    write_csv(outdir / "route_point.csv", ["hookup", "seq", "x", "y", "z"], [list(r) for r in rows])
    files.append("route_point.csv")
    return files


# --- queries used by the CLI and the planner ---------------------------------------------
def header_load(conn: sqlite3.Connection, system: str | None = None) -> list[dict]:
    q = "SELECT header, system, capacity, connected_load, remaining FROM v_header_load"
    args: tuple = ()
    if system:
        q += " WHERE system = ?"
        args = (system,)
    cols = ["header", "system", "capacity", "connected_load", "remaining"]
    return [dict(zip(cols, r)) for r in conn.execute(q + " ORDER BY header", args)]


def free_pocs(conn: sqlite3.Connection, system: str | None = None) -> list[dict]:
    q = "SELECT id, header, system, x, y, z, size, rated_flow FROM v_free_poc"
    args: tuple = ()
    if system:
        q += " WHERE system = ?"
        args = (system,)
    cols = ["id", "header", "system", "x", "y", "z", "size", "rated_flow"]
    return [dict(zip(cols, r)) for r in conn.execute(q + " ORDER BY id", args)]


def demand_totals(conn: sqlite3.Connection) -> list[dict]:
    cols = ["status", "system", "total_flow", "n"]
    return [dict(zip(cols, r)) for r in
            conn.execute("SELECT status, system, total_flow, n FROM v_tool_demand_total ORDER BY status, system")]


def tool_hookups(conn: sqlite3.Connection, tool: str) -> list[dict]:
    cols = ["id", "system", "poc", "header", "status", "size"]
    q = ("SELECT k.id, k.system, k.poc, p.header, k.status, k.size FROM hookup k JOIN poc p ON p.id = k.poc "
         "WHERE k.tool = ? ORDER BY k.system")
    return [dict(zip(cols, r)) for r in conn.execute(q, (tool,))]
