"""IFC4 model of the (illustrative) sub-fab: write a site to IFC and read it back.

Elements
  IfcGrid + IfcColumn            structural grid and columns
  IfcPipeSegment / IfcDuctSegment / IfcCableSegment (BUSBARSEGMENT)   utility headers
  IfcValve / IfcDamper / IfcProtectiveDevice                          points of connection
  IfcBuildingElementProxy (ObjectType ProcessTool / SupportEquipment) tools and sub-fab equipment
  IfcPipeSegment / IfcDuctSegment / IfcCableSegment (CABLESEGMENT)    hookup routes
  IfcDistributionSystem                                               one per utility system
Connectivity
  IfcDistributionPort nested (IfcRelNests) on headers, POCs, hookups and tools, joined by
  IfcRelConnectsPorts: header -> POC -> hookup start, hookup end -> tool connection.
Project-specific data live in property sets prefixed ``THP_`` (not buildingSMART Pset_);
quantities carry measure types and units (kPa, L/min, m3/h, Sm3/h, kVA, m/s, day, CU).
Geometry is read back from placements and solids, attributes from the property sets.
"""
from __future__ import annotations

import uuid

import ifcopenshell
import ifcopenshell.util.element as uel
import ifcopenshell.util.placement as upl

from . import engineering as E
from .numfmt import r10

NS = uuid.UUID("8f6d7c1e-2b55-4c39-9a51-6a0f2f6d3e11")
TIMESTAMP = "2026-01-01T00:00:00"
VIEW_DEFINITION = "ViewDefinition [ReferenceView_V1.2]"
HEADER_CLASS = {"liquid": ("IfcPipeSegment", "RIGIDSEGMENT"), "gas": ("IfcPipeSegment", "RIGIDSEGMENT"),
                "exhaust": ("IfcDuctSegment", "RIGIDSEGMENT"), "power": ("IfcCableSegment", "BUSBARSEGMENT")}
ROUTE_CLASS = {"liquid": ("IfcPipeSegment", "RIGIDSEGMENT"), "gas": ("IfcPipeSegment", "RIGIDSEGMENT"),
               "exhaust": ("IfcDuctSegment", "RIGIDSEGMENT"), "power": ("IfcCableSegment", "CABLESEGMENT")}
POC_CLASS = {"liquid": ("IfcValve", "ISOLATING"), "gas": ("IfcValve", "ISOLATING"),
             "exhaust": ("IfcDamper", "BALANCINGDAMPER"), "power": ("IfcProtectiveDevice", "CIRCUITBREAKER")}
PORT_TYPE = {"liquid": "PIPE", "gas": "PIPE", "exhaust": "DUCT", "power": "CABLE"}
DIST_TYPE = {"CDA": "COMPRESSEDAIR", "GEX": "EXHAUST", "AEX": "EXHAUST", "SEX": "EXHAUST", "PWR": "ELECTRICAL"}
LENGTH_KEYS = {"step", "subfab_height", "fab_floor_z"}
PRESSURE_MEANING = {"supply": "minimum inlet pressure, kPa gauge", "return": "pressure drop across the tool, kPa",
                    "exhaust": "required port static pressure, kPa gauge", "power": "not used"}


def guid(name: str) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(NS, name).hex)


class Writer:
    def __init__(self, title: str):
        f = ifcopenshell.file(schema="IFC4")
        f.header.file_description.description = (VIEW_DEFINITION,)
        f.header.file_name.name = title
        f.header.file_name.time_stamp = TIMESTAMP
        f.header.file_name.author = ("tool-hookup-planner",)
        f.header.file_name.organization = ("illustrative",)
        self.f = f
        self.origin = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0)), None, None)
        metre = f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
        m3 = f.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE")
        units = f.createIfcUnitAssignment([metre, f.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE"), m3])
        self._units(metre, m3)
        self.ctx = f.createIfcGeometricRepresentationContext(None, "Model", 3, 1.0e-5, self.origin, None)
        self.body = f.createIfcGeometricRepresentationSubContext("Body", "Model", None, None, None, None,
                                                                 self.ctx, None, "MODEL_VIEW", None)
        self.footprint = f.createIfcGeometricRepresentationSubContext("FootPrint", "Model", None, None, None,
                                                                      None, self.ctx, None, "MODEL_VIEW", None)
        self.project = f.createIfcProject(guid("project"), None, "Illustrative sub-fab", None, None, None, None,
                                          [self.ctx], units)
        self.nested: dict = {}     # element -> [ports], written as IfcRelNests at the end

    def _units(self, metre, m3):
        f = self.f
        dims = lambda *e: f.createIfcDimensionalExponents(*e)
        second = f.createIfcSIUnit(None, "TIMEUNIT", None, "SECOND")

        def conv(utype, name, dim, factor, measure, base):
            return f.createIfcConversionBasedUnit(dim, utype, name, f.createIfcMeasureWithUnit(
                f.create_entity(measure, factor), base))
        litre = conv("VOLUMEUNIT", "litre", dims(3, 0, 0, 0, 0, 0, 0), 0.001, "IfcVolumeMeasure", m3)
        minute = conv("TIMEUNIT", "minute", dims(0, 0, 1, 0, 0, 0, 0), 60.0, "IfcTimeMeasure", second)
        hour = conv("TIMEUNIT", "hour", dims(0, 0, 1, 0, 0, 0, 0), 3600.0, "IfcTimeMeasure", second)
        day = conv("TIMEUNIT", "day", dims(0, 0, 1, 0, 0, 0, 0), 86400.0, "IfcTimeMeasure", second)
        el = lambda u, e: f.createIfcDerivedUnitElement(u, e)
        kv = f.createIfcSIUnit(None, "ELECTRICVOLTAGEUNIT", "KILO", "VOLT")
        amp = f.createIfcSIUnit(None, "ELECTRICCURRENTUNIT", None, "AMPERE")
        self.u = {
            "kPa": f.createIfcSIUnit(None, "PRESSUREUNIT", "KILO", "PASCAL"),
            "L/min": f.createIfcDerivedUnit([el(litre, 1), el(minute, -1)], "VOLUMETRICFLOWRATEUNIT", None),
            "m3/h": f.createIfcDerivedUnit([el(m3, 1), el(hour, -1)], "VOLUMETRICFLOWRATEUNIT", None),
            "Sm3/h": f.createIfcDerivedUnit([el(m3, 1), el(hour, -1)], "USERDEFINED",
                                            "standard cubic metre per hour (15 degC, 101.325 kPa)"),
            "kVA": f.createIfcDerivedUnit([el(kv, 1), el(amp, 1)], "USERDEFINED", "kilovolt-ampere"),
            "m/s": f.createIfcDerivedUnit([el(metre, 1), el(second, -1)], "LINEARVELOCITYUNIT", None),
            "day": day,
            "CU": f.createIfcMonetaryUnit("CU"),
        }

    def flow(self, unit: str, value: float):
        measure = "IfcReal" if unit == "kVA" else "IfcVolumetricFlowRateMeasure"
        return (measure, value, self.u[unit])

    # --- primitives ---------------------------------------------------------------------
    def pt(self, p):
        return self.f.createIfcCartesianPoint(tuple(float(v) for v in p))

    def placement(self, loc, rel=None):
        return self.f.createIfcLocalPlacement(rel, self.f.createIfcAxis2Placement3D(self.pt(loc), None, None))

    def shape(self, items, rep_type="SweptSolid", ctx=None):
        rep = self.f.createIfcShapeRepresentation(ctx or self.body, (ctx or self.body).ContextIdentifier,
                                                  rep_type, items)
        return self.f.createIfcProductDefinitionShape(None, None, [rep])

    def box(self, w, d, h):
        prof = self.f.createIfcRectangleProfileDef("AREA", None, self.f.createIfcAxis2Placement2D(
            self.f.createIfcCartesianPoint((0.0, 0.0)), None), float(w), float(d))
        solid = self.f.createIfcExtrudedAreaSolid(prof, self.origin, self.f.createIfcDirection((0.0, 0.0, 1.0)),
                                                  float(h))
        return self.shape([solid])

    def disk(self, pts, radius):
        line = self.f.createIfcPolyline([self.pt(p) for p in pts])
        solid = self.f.createIfcSweptDiskSolid(line, float(radius), None, None, None)
        return self.shape([solid], "AdvancedSweptSolid")

    def pset(self, owner, name: str, props: dict):
        """Property set; a value given as (measure type, value, unit) is written with its unit."""
        vals = []
        for k, v in props.items():
            unit = None
            if isinstance(v, tuple):
                mtype, val, unit = v
                nv = self.f.create_entity(mtype, float(val))
            elif isinstance(v, bool):
                nv = self.f.createIfcBoolean(v)
            elif isinstance(v, int):
                nv = self.f.createIfcInteger(v)
            elif isinstance(v, float):
                nv = self.f.createIfcReal(v)
            else:
                nv = self.f.createIfcLabel(str(v))
            vals.append(self.f.createIfcPropertySingleValue(k, None, nv, unit))
        ps = self.f.createIfcPropertySet(guid(f"{owner.GlobalId}/{name}"), None, name, None, vals)
        self.f.createIfcRelDefinesByProperties(guid(f"{owner.GlobalId}/{name}/rel"), None, None, None, [owner], ps)

    def element(self, cls, key, name, placement, shape, predefined=None, object_type=None):
        f = self.f
        if predefined is not None:
            return f.create_entity(cls, GlobalId=guid(key), Name=name, ObjectType=object_type,
                                   ObjectPlacement=placement, Representation=shape, PredefinedType=predefined)
        return f.create_entity(cls, GlobalId=guid(key), Name=name, ObjectType=object_type,
                               ObjectPlacement=placement, Representation=shape)

    def port(self, owner, key: str, name: str, loc, rel_pl, direction: str, kind: str, system: str):
        p = self.f.create_entity("IfcDistributionPort", GlobalId=guid(f"port/{key}"), Name=name,
                                 ObjectPlacement=self.placement(loc, rel_pl), FlowDirection=direction,
                                 PredefinedType=PORT_TYPE[kind], SystemType=DIST_TYPE.get(system, "NOTDEFINED"))
        self.nested.setdefault(owner, []).append(p)
        return p

    def connect(self, upstream, downstream, key: str):
        self.f.createIfcRelConnectsPorts(guid(f"conn/{key}"), None, None, None, upstream, downstream, None)


def _dirs(role: str) -> tuple[str, str]:
    """(direction of the upstream port, direction of the downstream port) in the supply sense."""
    return ("SOURCE", "SINK") if role == "supply" else ("SINK", "SOURCE")


def write_ifc(site: dict, path, new_hookups: list | None = None, title="subfab.ifc") -> None:
    """Write the site; ``new_hookups`` (planned routes) are added with Status=planned."""
    w = Writer(title)
    f = w.f
    m = site["meta"]
    site_pl = w.placement((0, 0, 0))
    ifc_site = f.createIfcSite(guid("site"), None, "Site", None, None, site_pl, None, None, "ELEMENT",
                               None, None, None, None, None)
    bld_pl = w.placement((0, 0, 0), site_pl)
    bld = f.createIfcBuilding(guid("building"), None, "Illustrative fab building", None, None, bld_pl, None,
                              None, "ELEMENT", None, None, None)
    sub_pl = w.placement((0, 0, 0), bld_pl)
    fab_pl = w.placement((0, 0, E.FAB_FLOOR_Z), bld_pl)
    subfab = f.createIfcBuildingStorey(guid("storey/subfab"), None, "SubFab", None, None, sub_pl, None, None,
                                       "ELEMENT", 0.0)
    fab = f.createIfcBuildingStorey(guid("storey/fab"), None, "Fab", None, None, fab_pl, None, None,
                                    "ELEMENT", float(E.FAB_FLOOR_Z))
    f.createIfcRelAggregates(guid("agg/project"), None, None, None, w.project, [ifc_site])
    f.createIfcRelAggregates(guid("agg/site"), None, None, None, ifc_site, [bld])
    f.createIfcRelAggregates(guid("agg/building"), None, None, None, bld, [subfab, fab])
    w.pset(bld, "THP_Model", {k: (("IfcLengthMeasure", v, None) if k in LENGTH_KEYS else
                                  (float(v) if isinstance(v, float) else v)) for k, v in sorted(m.items())})

    in_sub, in_fab = [], []
    groups: dict[str, list] = {s["code"]: [] for s in site["systems"]}
    kinds = {s["code"]: s["kind"] for s in site["systems"]}
    roles = {s["code"]: s["role"] for s in site["systems"]}
    units = {s["code"]: s["flow_unit"] for s in site["systems"]}

    # structural grid
    xs = sorted({c["x"] for c in site["columns"]})
    ys = sorted({c["y"] for c in site["columns"]})
    def axis(tag, a, b):
        return f.createIfcGridAxis(tag, f.createIfcPolyline([f.createIfcCartesianPoint(a),
                                                              f.createIfcCartesianPoint(b)]), True)
    u = [axis(f"X{n + 1}", (float(x), float(ys[0])), (float(x), float(ys[-1]))) for n, x in enumerate(xs)]
    v = [axis(f"Y{n + 1}", (float(xs[0]), float(y)), (float(xs[-1]), float(y))) for n, y in enumerate(ys)]
    curves = f.createIfcGeometricCurveSet([a.AxisCurve for a in u + v])
    grid = f.createIfcGrid(guid("grid"), None, "Structural grid", None, None, w.placement((0, 0, 0), sub_pl),
                           w.shape([curves], "GeometricCurveSet", w.footprint), u, v, None, None)
    in_sub.append(grid)

    for c in site["columns"]:
        el = w.element("IfcColumn", f"col/{c['id']}", c["id"], w.placement((c["x"], c["y"], c["z0"]), sub_pl),
                       w.box(c["w"], c["d"], c["z1"] - c["z0"]), "COLUMN")
        in_sub.append(el)

    hdr_el = {}
    for h in site["headers"]:
        cls, pdt = HEADER_CLASS[kinds[h["system"]]]
        el = w.element(cls, f"hdr/{h['id']}", h["id"], w.placement((h["x0"], h["y"], h["z"]), sub_pl),
                       w.disk([(0, 0, 0), (h["x1"] - h["x0"], 0, 0)], h["od"] / 2), pdt, "UtilityHeader")
        un = units[h["system"]]
        w.pset(el, "THP_Header", {"System": h["system"], "Corridor": h["corridor"],
                                  "Capacity": w.flow(un, h["capacity"]),
                                  "PressureKPaG": ("IfcPressureMeasure", h["pressure_kpa_g"], w.u["kPa"]),
                                  "UpgradeStep": w.flow(un, h["upgrade_step"]),
                                  "UpgradeCost": ("IfcMonetaryMeasure", h["upgrade_cost"], w.u["CU"]),
                                  "UpgradeDays": ("IfcTimeMeasure", h["upgrade_days"], w.u["day"])})
        in_sub.append(el)
        groups[h["system"]].append(el)
        hdr_el[h["id"]] = el

    poc_out = {}
    for p in site["pocs"]:
        kind = kinds[p["system"]]
        cls, pdt = POC_CLASS[kind]
        size = E.size_by_label(p["system"], p["size"])
        loc = (p["x"], p["y"], p["z"])
        el = w.element(cls, f"poc/{p['id']}", p["id"], w.placement(loc, sub_pl),
                       w.disk([(0, 0, 0), (0, 0, 0.25)], size["od"] / 2), pdt, "PointOfConnection")
        w.pset(el, "THP_POC", {"Header": p["header"], "System": p["system"], "NominalSize": p["size"],
                               "RatedFlow": w.flow(units[p["system"]], p["rated_flow"]), "Status": p["status"]})
        in_sub.append(el)
        groups[p["system"]].append(el)
        up, down = _dirs(roles[p["system"]])
        hp = w.port(hdr_el[p["header"]], f"hdr/{p['id']}", f"{p['header']}->{p['id']}", loc, sub_pl, up, kind,
                    p["system"])
        pin = w.port(el, f"poc-in/{p['id']}", f"{p['id']}/header side", loc, sub_pl, down, kind, p["system"])
        poc_out[p["id"]] = w.port(el, f"poc-out/{p['id']}", f"{p['id']}/hookup side", loc, sub_pl, up, kind,
                                  p["system"])
        w.connect(hp, pin, f"hdr-poc/{p['id']}")

    for q in site["equipment"]:
        cx, cy = (q["x0"] + q["x1"]) / 2, (q["y0"] + q["y1"]) / 2
        el = w.element("IfcBuildingElementProxy", f"eq/{q['id']}", q["id"], w.placement((cx, cy, q["z0"]), sub_pl),
                       w.box(q["x1"] - q["x0"], q["y1"] - q["y0"], q["z1"] - q["z0"]), "NOTDEFINED",
                       "SupportEquipment")
        in_sub.append(el)

    dem_by_tool: dict[str, list] = {}
    for d in site["demands"]:
        dem_by_tool.setdefault(d["tool"], []).append(d)
    tool_port = {}
    for t in site["tools"]:
        cx, cy = (t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2
        el = w.element("IfcBuildingElementProxy", f"tool/{t['id']}", t["id"], w.placement((cx, cy, 0.0), fab_pl),
                       w.box(t["x1"] - t["x0"], t["y1"] - t["y0"], t["height"]), "NOTDEFINED", "ProcessTool")
        w.pset(el, "THP_Tool", {"Category": t["category"], "Status": t["status"]})
        for d in dem_by_tool.get(t["id"], []):
            sysc = d["system"]
            meaning = "power" if kinds[sysc] == "power" else roles[sysc]
            w.pset(el, f"THP_Demand_{sysc}", {
                "Flow": w.flow(units[sysc], d["flow"]),
                "Pressure": ("IfcPressureMeasure", d["p_req"], w.u["kPa"]), "PressureMeaning": PRESSURE_MEANING[meaning],
                "PenetrationX": ("IfcLengthMeasure", d["px"], None), "PenetrationY": ("IfcLengthMeasure", d["py"], None)})
            _, down = _dirs(roles[sysc])
            tool_port[(t["id"], sysc)] = w.port(el, f"tool/{t['id']}/{sysc}", f"{t['id']}/{sysc}",
                                                (d["px"], d["py"], E.FAB_FLOOR_Z), sub_pl, down, kinds[sysc], sysc)
        in_fab.append(el)

    all_hk = [(hk, hk["status"]) for hk in site["hookups"]] + [(hk, "planned") for hk in (new_hookups or [])]
    for hk, status in all_hk:
        kind = kinds[hk["system"]]
        cls, pdt = ROUTE_CLASS[kind]
        size = E.size_by_label(hk["system"], hk["size"])
        el = w.element(cls, f"hk/{hk['id']}", hk["id"], w.placement((0, 0, 0), sub_pl),
                       w.disk([tuple(p) for p in hk["points"]], size["od"] / 2), pdt, "Hookup")
        w.pset(el, "THP_Hookup", {"Tool": hk["tool"], "System": hk["system"], "POC": hk["poc"],
                                  "Status": status, "NominalSize": hk["size"]})
        in_sub.append(el)
        groups[hk["system"]].append(el)
        up, down = _dirs(roles[hk["system"]])
        start = w.port(el, f"hk-start/{hk['id']}", f"{hk['id']}/POC end", hk["points"][0], sub_pl, down, kind,
                       hk["system"])
        end = w.port(el, f"hk-end/{hk['id']}", f"{hk['id']}/tool end", hk["points"][-1], sub_pl, up, kind,
                     hk["system"])
        w.connect(poc_out[hk["poc"]], start, f"poc-hk/{hk['id']}")
        w.connect(end, tool_port[(hk["tool"], hk["system"])], f"hk-tool/{hk['id']}")

    f.createIfcRelContainedInSpatialStructure(guid("contain/subfab"), None, None, None, in_sub, subfab)
    f.createIfcRelContainedInSpatialStructure(guid("contain/fab"), None, None, None, in_fab, fab)
    for owner, ports in w.nested.items():
        f.createIfcRelNests(guid(f"nest/{owner.GlobalId}"), None, None, None, owner, ports)
    for s in site["systems"]:
        ds = f.create_entity("IfcDistributionSystem", GlobalId=guid(f"sys/{s['code']}"), Name=s["code"],
                             Description=s["name"], ObjectType=s["code"],
                             PredefinedType=DIST_TYPE.get(s["code"], "USERDEFINED"))
        w.pset(ds, "THP_System", {"Kind": s["kind"], "Role": s["role"], "Fluid": s["fluid"],
                                  "FlowUnit": s["flow_unit"], "Material": s["material"],
                                  "VMax": ("IfcLinearVelocityMeasure", s["v_max"], w.u["m/s"]),
                                  "CoincidenceFactor": float(s["coincidence_factor"])})
        if groups[s["code"]]:
            f.createIfcRelAssignsToGroup(guid(f"grp/{s['code']}"), None, None, None, groups[s["code"]], None, ds)
    # write with LF line endings on every platform (f.write uses the OS convention)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f.to_string())


# --- reading ---------------------------------------------------------------------------
def _loc(el):
    mtx = upl.get_local_placement(el.ObjectPlacement)
    return tuple(r10(float(mtx[a][3])) for a in range(3))


def _solid(el):
    return el.Representation.Representations[0].Items[0]


def read_ifc(path) -> dict:
    """Rebuild a site dict from an IFC written by :func:`write_ifc` (hookups: existing only)."""
    f = ifcopenshell.open(str(path))
    bld = f.by_type("IfcBuilding")[0]
    meta = {k: v for k, v in uel.get_pset(bld, "THP_Model").items() if k != "id"}
    site = {"meta": meta, "systems": [], "columns": [], "headers": [], "pocs": [], "equipment": [],
            "tools": [], "demands": [], "hookups": []}
    for ds in f.by_type("IfcDistributionSystem"):
        ps = uel.get_pset(ds, "THP_System")
        site["systems"].append({"code": ds.Name, "name": ds.Description, "kind": ps["Kind"], "role": ps["Role"],
                                "fluid": ps["Fluid"], "flow_unit": ps["FlowUnit"], "material": ps["Material"],
                                "v_max": ps["VMax"], "coincidence_factor": ps["CoincidenceFactor"]})
    for c in f.by_type("IfcColumn"):
        x, y, z = _loc(c)
        s = _solid(c)
        site["columns"].append({"id": c.Name, "x": x, "y": y, "w": r10(s.SweptArea.XDim),
                                "d": r10(s.SweptArea.YDim), "z0": z, "z1": r10(z + s.Depth)})
    for el in f.by_type("IfcFlowSegment"):
        if el.ObjectType != "UtilityHeader":
            continue
        x, y, z = _loc(el)
        s = _solid(el)
        ps = uel.get_pset(el, "THP_Header")
        site["headers"].append({"id": el.Name, "system": ps["System"], "corridor": ps["Corridor"], "y": y, "z": z,
                                "x0": x, "x1": r10(x + s.Directrix.Points[-1].Coordinates[0]),
                                "od": r10(2 * s.Radius), "capacity": ps["Capacity"],
                                "pressure_kpa_g": ps["PressureKPaG"], "upgrade_step": ps["UpgradeStep"],
                                "upgrade_cost": ps["UpgradeCost"], "upgrade_days": ps["UpgradeDays"]})
    for el in f.by_type("IfcDistributionFlowElement") + f.by_type("IfcDistributionControlElement"):
        if el.ObjectType != "PointOfConnection":
            continue
        ps = uel.get_pset(el, "THP_POC")
        if ps is None:
            continue
        x, y, z = _loc(el)
        site["pocs"].append({"id": el.Name, "header": ps["Header"], "system": ps["System"], "x": x, "y": y, "z": z,
                             "size": ps["NominalSize"], "rated_flow": ps["RatedFlow"], "status": ps["Status"]})
    for el in f.by_type("IfcBuildingElementProxy"):
        s = _solid(el)
        x, y, z = _loc(el)
        hx, hy = s.SweptArea.XDim / 2, s.SweptArea.YDim / 2
        if el.ObjectType == "SupportEquipment":
            site["equipment"].append({"id": el.Name, "x0": r10(x - hx), "y0": r10(y - hy), "z0": z,
                                      "x1": r10(x + hx), "y1": r10(y + hy), "z1": r10(z + s.Depth)})
        elif el.ObjectType == "ProcessTool":
            ps = uel.get_pset(el, "THP_Tool")
            site["tools"].append({"id": el.Name, "category": ps["Category"], "status": ps["Status"],
                                  "x0": r10(x - hx), "y0": r10(y - hy), "x1": r10(x + hx), "y1": r10(y + hy),
                                  "height": r10(s.Depth)})
            for name, props in sorted(uel.get_psets(el).items()):
                if name.startswith("THP_Demand_"):
                    site["demands"].append({"tool": el.Name, "system": name[len("THP_Demand_"):],
                                            "flow": props["Flow"], "p_req": props["Pressure"],
                                            "px": props["PenetrationX"], "py": props["PenetrationY"]})
    for el in f.by_type("IfcFlowSegment"):
        if el.ObjectType != "Hookup":
            continue
        ps = uel.get_pset(el, "THP_Hookup")
        if ps["Status"] == "planned":
            continue
        ox, oy, oz = _loc(el)
        pts = [[r10(ox + p.Coordinates[0]), r10(oy + p.Coordinates[1]), r10(oz + p.Coordinates[2])]
               for p in _solid(el).Directrix.Points]
        site["hookups"].append({"id": el.Name, "tool": ps["Tool"], "system": ps["System"], "poc": ps["POC"],
                                "status": ps["Status"], "size": ps["NominalSize"], "points": pts})
    return site


def port_connectivity(path) -> dict:
    """Follow IfcRelNests + IfcRelConnectsPorts and compare with the THP_ property sets.

    For every hookup the element on the far side of its POC-end port must be the POC named in
    THP_Hookup and the element on the far side of its tool-end port must be the tool; for every
    POC the element on the far side of its header-side port must be the header in THP_POC.
    """
    f = ifcopenshell.open(str(path))
    owner = {}
    for rel in f.by_type("IfcRelNests"):
        for p in rel.RelatedObjects:
            if p.is_a("IfcDistributionPort"):
                owner[p.id()] = rel.RelatingObject
    linked: dict[int, list] = {}
    for rel in f.by_type("IfcRelConnectsPorts"):
        a, b = owner[rel.RelatingPort.id()], owner[rel.RelatedPort.id()]
        linked.setdefault(a.id(), []).append(b)
        linked.setdefault(b.id(), []).append(a)
    mism, n_hk, n_poc = [], 0, 0
    for el in f.by_type("IfcFlowSegment"):
        if el.ObjectType != "Hookup":
            continue
        n_hk += 1
        ps = uel.get_pset(el, "THP_Hookup")
        nb = linked.get(el.id(), [])
        pocs = sorted(x.Name for x in nb if x.ObjectType == "PointOfConnection")
        tools = sorted(x.Name for x in nb if x.ObjectType == "ProcessTool")
        if pocs != [ps["POC"]] or tools != [ps["Tool"]]:
            mism.append(el.Name)
    for el in f.by_type("IfcDistributionFlowElement") + f.by_type("IfcDistributionControlElement"):
        if el.ObjectType != "PointOfConnection":
            continue
        n_poc += 1
        hdrs = sorted(x.Name for x in linked.get(el.id(), []) if x.ObjectType == "UtilityHeader")
        if hdrs != [uel.get_pset(el, "THP_POC")["Header"]]:
            mism.append(el.Name)
    return {"hookups_checked": n_hk, "pocs_checked": n_poc, "ports": len(f.by_type("IfcDistributionPort")),
            "port_connections": len(f.by_type("IfcRelConnectsPorts")), "mismatches": sorted(mism)}
