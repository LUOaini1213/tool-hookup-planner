"""Site data structure helpers: indexing, solids, lattice, header loads, hookup evaluation.

A *site* is a plain JSON-able dict (see docs/method.md, section 1):
meta, systems, columns, headers, pocs, equipment, tools, demands, hookups.
"""
from __future__ import annotations

from . import engineering as E
from . import hydraulics as H
from .geometry import Solid, polyline_solids
from .lattice import Lattice, bends, compress, length


class Index:
    def __init__(self, site: dict):
        self.site = site
        self.headers = {h["id"]: h for h in site["headers"]}
        self.pocs = {p["id"]: p for p in site["pocs"]}
        self.tools = {t["id"]: t for t in site["tools"]}
        self.demand = {(d["tool"], d["system"]): d for d in site["demands"]}
        self.columns = {c["id"]: c for c in site["columns"]}


def as_built(site: dict) -> dict:
    """Copy of the site without planned hookups and planned (not yet built) POCs."""
    out = dict(site)
    out["hookups"] = [h for h in site["hookups"] if h["status"] != "planned"]
    out["pocs"] = [p for p in site["pocs"] if p["status"] != "planned"]
    return out


def static_solids(site: dict) -> list[Solid]:
    out = []
    for c in site["columns"]:
        out.append(Solid(c["id"], "column", (c["x"] - c["w"] / 2, c["y"] - c["d"] / 2, c["z0"]),
                         (c["x"] + c["w"] / 2, c["y"] + c["d"] / 2, c["z1"]), 0.0, c["id"]))
    for h in site["headers"]:
        out.append(Solid(h["id"], "header", (h["x0"], h["y"], h["z"]), (h["x1"], h["y"], h["z"]),
                         h["od"] / 2, h["id"]))
    for q in site["equipment"]:
        out.append(Solid(q["id"], "equipment", (q["x0"], q["y0"], q["z0"]), (q["x1"], q["y1"], q["z1"]),
                         0.0, q["id"]))
    return out


def route_od(system: str, size_label: str) -> float:
    return E.size_by_label(system, size_label)["od"]


def hookup_solids(hk: dict) -> list[Solid]:
    return polyline_solids(hk["id"], [tuple(p) for p in hk["points"]],
                           route_od(hk["system"], hk["size"]) / 2,
                           meta={"tool": hk["tool"], "system": hk["system"], "poc": hk["poc"]})


def build_lattice(site: dict, include_hookups=True) -> Lattice:
    m = site["meta"]
    lat = Lattice(m["step"], m["nx"], m["ny"], m["nz"], m["kmin"], m["kmax"])
    lat.set_static(static_solids(site))
    for d in site["demands"]:
        lat.reserve_penetration(d["px"], d["py"])
    if include_hookups:
        for hk in site["hookups"]:
            lat.add_route(hookup_solids(hk))
    return lat


def header_loads(site: dict) -> dict:
    """Connected load per header from hookups whose tools are in service (coincidence-weighted)."""
    idx = Index(site)
    load = {h["id"]: 0.0 for h in site["headers"]}
    for hk in site["hookups"]:
        if hk["status"] not in ("released", "installed", "tested"):
            continue
        hdr = idx.pocs[hk["poc"]]["header"]
        d = idx.demand[(hk["tool"], hk["system"])]
        load[hdr] += d["flow"] * E.COINCIDENCE_FACTOR[hk["system"]]
    return load


def dz_flow(system: str, poc_z: float) -> float:
    """Elevation change in the flow direction (supply flows up from the POC to the tool)."""
    if E.SYSTEMS[system]["role"] == "supply":
        return E.FAB_FLOOR_Z - poc_z
    return poc_z - E.FAB_FLOOR_Z


def tool_side_pressure(system: str, p_req: float, supply: tuple | None = None) -> float | None:
    """Pressure condition at the tool end of a hookup, in kPa gauge.

    For every system except the PCW return this is the demand's ``p_req`` (minimum inlet
    pressure, or required exhaust port static pressure).  For PCWR, ``p_req`` is the tool's
    internal pressure drop (ILLUSTRATIVE), and the outlet pressure follows from the tool's
    PCW supply hookup: ``supply`` = (supply header pressure, supply hookup loss).  Returns
    None for a PCW return whose supply is unknown.
    """
    if system != E.PCW_PAIR[1]:
        return p_req
    if supply is None:
        return None
    return H.pcw_outlet_kpa_g(supply[0], supply[1], p_req)


def corridor_of(site: dict, poc_id: str) -> str | None:
    idx = Index(site)
    p = idx.pocs.get(poc_id)
    return idx.headers[p["header"]]["corridor"] if p else None


def evaluate_hookup(site: dict, system: str, flow: float, tool_p: float, poc: dict, points: list,
                    size_label: str) -> dict:
    """Velocity / pressure / rating checks for a hookup of a given size and route.

    ``tool_p`` is the tool-side pressure from :func:`tool_side_pressure`.
    """
    hdr = Index(site).headers[poc["header"]]
    pts = [tuple(p) for p in points]
    L = length(pts)
    nb = bends(pts)
    size = E.size_by_label(system, size_label)
    ev = H.evaluate_size(system, size, flow, L, nb, dz_flow(system, poc["z"]), hdr["pressure_kpa_g"], tool_p)
    ev.update({"length_m": L, "bends": nb})
    return ev


def route_points(lat: Lattice, stub: list[int], path: list[int], pen_xy) -> list:
    pts = [lat.xyz(n) for n in stub] + [lat.xyz(n) for n in path[1:]]
    pts.append((pen_xy[0], pen_xy[1], E.FAB_FLOOR_Z))
    return compress(pts)


def route_one(site: dict, lat: Lattice, system: str, flow: float, tool_p: float, poc: dict, pen_xy,
              max_resize: int = 3) -> dict:
    """Route one hookup with A*, size it on the routed length, re-route if it grew.

    ``tool_p`` is the tool-side pressure from :func:`tool_side_pressure`.
    Returns dict(points, size, eval, cost, governed_by) or dict(error=...).
    """
    hdr = Index(site).headers[poc["header"]]
    prov = H.min_size_velocity(system, flow, hdr["pressure_kpa_g"])
    if prov is None:
        return {"error": "no catalogue size meets the velocity limit"}
    size = prov
    goal = lat.snap(pen_xy[0], pen_xy[1], (lat.kmax + 1) * lat.step)
    for _ in range(max_resize):
        r = size["od"] / 2
        poc_node = lat.snap(poc["x"], poc["y"], poc["z"])
        stub = lat.stub(poc["header"], poc_node, r, E.CLEARANCE_M)
        if stub is None:
            return {"error": "take-off blocked"}
        free = lat.free_mask(r, E.CLEARANCE_M, goal)
        for n in stub[:-1]:
            free[n] = 0
        path, cost = lat.astar(free, stub[-1], 4, goal)
        if path is None:
            return {"error": "no path"}
        pts = route_points(lat, stub, path, pen_xy)
        sel = H.select_size(system, flow, length(pts), bends(pts), dz_flow(system, poc["z"]),
                            hdr["pressure_kpa_g"], tool_p)
        if sel["size"] is None:
            return {"error": "no catalogue size passes velocity and pressure checks", "points": pts}
        if E.size_index(system, sel["size"]["label"]) <= E.size_index(system, size["label"]):
            return {"points": pts, "size": sel["size"]["label"], "eval": sel["eval"],
                    "governed_by": sel["governed_by"], "astar_cost": cost,
                    "stub_nodes": len(stub), "path_nodes": len(path)}
        size = sel["size"]
    return {"error": "size did not converge"}
