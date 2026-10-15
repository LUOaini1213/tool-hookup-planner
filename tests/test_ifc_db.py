import sqlite3

import ifcopenshell
import pytest

from hookup_planner import db as DB
from hookup_planner import ifc_io
from hookup_planner.model import header_loads


@pytest.fixture(scope="module")
def ifc_path(small_site, tmp_path_factory):
    p = tmp_path_factory.mktemp("ifc") / "small.ifc"
    ifc_io.write_ifc(small_site, p)
    return p


def test_ifc_round_trip_is_exact(small_site, ifc_path):
    back = ifc_io.read_ifc(ifc_path)
    a, b = DB.canonical_site(small_site), DB.canonical_site(back)
    for key in a:
        assert a[key] == b[key], key


def test_ifc_entities_and_schema(small_site, ifc_path):
    f = ifcopenshell.open(str(ifc_path))
    assert f.schema == "IFC4"
    assert len(f.by_type("IfcColumn")) == len(small_site["columns"]) == 4 * 4
    headers = [e for e in f.by_type("IfcFlowSegment") if e.ObjectType == "UtilityHeader"]
    assert len(headers) == len(small_site["headers"]) == 14
    assert {e.is_a() for e in headers} == {"IfcPipeSegment", "IfcDuctSegment", "IfcCableSegment"}
    assert len(f.by_type("IfcDistributionSystem")) == 9
    assert len(f.by_type("IfcGrid")) == 1
    assert len(f.by_type("IfcGrid")[0].UAxes) == 4 and len(f.by_type("IfcGrid")[0].VAxes) == 4
    tools = [e for e in f.by_type("IfcBuildingElementProxy") if e.ObjectType == "ProcessTool"]
    assert len(tools) == 6
    # tools sit on the fab level, 6.6 m above the sub-fab floor
    import ifcopenshell.util.placement as upl
    assert all(abs(upl.get_local_placement(t.ObjectPlacement)[2][3] - 6.6) < 1e-9 for t in tools)
    for e in f.by_type("IfcRoot"):
        assert len(e.GlobalId) == 22


def test_ifc_written_twice_is_byte_identical(small_site, tmp_path):
    a, b = tmp_path / "a.ifc", tmp_path / "b.ifc"
    ifc_io.write_ifc(small_site, a, title="x.ifc")
    ifc_io.write_ifc(small_site, b, title="x.ifc")
    assert a.read_bytes() == b.read_bytes()


def test_db_round_trip_and_views(small_site):
    conn = DB.connect()
    DB.write_site(conn, small_site)
    back = DB.read_site(conn)
    assert DB.canonical_site(back) == DB.canonical_site(small_site)
    loads = header_loads(small_site)
    rows = DB.header_load(conn)
    assert len(rows) == 14
    for r in rows:
        assert r["connected_load"] == pytest.approx(loads[r["header"]])
        assert r["remaining"] == pytest.approx(r["capacity"] - loads[r["header"]])
    used = {h["poc"] for h in small_site["hookups"]}
    free = DB.free_pocs(conn, "CDA")
    assert free and all(p["system"] == "CDA" and p["id"] not in used for p in free)
    assert len(DB.free_pocs(conn)) == len(small_site["pocs"]) - len(used)
    tot = {(r["status"], r["system"]): r["total_flow"] for r in DB.demand_totals(conn)}
    exp = sum(d["flow"] for d in small_site["demands"] if d["system"] == "N2" and d["tool"].startswith("T-N"))
    assert tot[("new", "N2")] == pytest.approx(exp)


def test_db_constraints_reject_bad_rows(small_site):
    conn = DB.connect()
    DB.write_site(conn, small_site)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO poc VALUES ('X', 'PCWS-A', 'PCWS', 1, 1, 1, 'NPS 1', 10, 'broken')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO hookup VALUES ('Y', 'T-NOPE', 'PCWS', 'PCWS-A-P01', 'planned', 'NPS 1')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tool_demand VALUES ('T-N01', 'CDA', -3, 600, 1, 1)")


def test_planned_records_do_not_load_headers(small_site, small_plan):
    conn = DB.connect()
    DB.write_site(conn, small_site)
    before = {r["header"]: r["connected_load"] for r in DB.header_load(conn)}
    DB.write_plan(conn, small_plan["site"], small_plan["hookups"])
    after = {r["header"]: r["connected_load"] for r in DB.header_load(conn)}
    assert before == after
    n = conn.execute("SELECT COUNT(*) FROM hookup WHERE status = 'planned'").fetchone()[0]
    assert n == len(small_plan["hookups"])
    hk = small_plan["hookups"][0]
    assert DB.tool_hookups(conn, hk["tool"])


def test_ifc_header_ports_and_units(small_site, ifc_path):
    f = ifcopenshell.open(str(ifc_path))
    assert f.header.file_description.description == ("ViewDefinition [ReferenceView_V1.2]",)
    assert f.header.file_name.author == ("tool-hookup-planner",)
    assert f.header.file_name.organization == ("illustrative",)
    con = ifc_io.port_connectivity(ifc_path)
    n_poc, n_hk, n_dem = len(small_site["pocs"]), len(small_site["hookups"]), len(small_site["demands"])
    assert con["mismatches"] == []
    assert con["hookups_checked"] == n_hk and con["pocs_checked"] == n_poc
    assert con["ports"] == 3 * n_poc + 2 * n_hk + n_dem
    assert con["port_connections"] == n_poc + 2 * n_hk
    hdr = next(e for e in f.by_type("IfcFlowSegment") if e.ObjectType == "UtilityHeader" and e.Name.startswith("PCWS"))
    props = {p.Name: p for r in hdr.IsDefinedBy for p in r.RelatingPropertyDefinition.HasProperties}
    p = props["PressureKPaG"]
    assert p.NominalValue.is_a("IfcPressureMeasure") and p.Unit.Prefix == "KILO" and p.Unit.Name == "PASCAL"
    u = props["Capacity"].Unit
    assert u.UnitType == "VOLUMETRICFLOWRATEUNIT"
    assert sorted((e.Unit.Name, e.Exponent) for e in u.Elements) == [("litre", 1), ("minute", -1)]


def test_ifc_port_check_detects_a_miswired_hookup(small_site, tmp_path):
    import copy
    site = copy.deepcopy(small_site)
    p = tmp_path / "bad.ifc"
    ifc_io.write_ifc(site, p)
    f = ifcopenshell.open(str(p))
    hk = next(e for e in f.by_type("IfcFlowSegment") if e.ObjectType == "Hookup")
    pset = next(r.RelatingPropertyDefinition for r in hk.IsDefinedBy if r.RelatingPropertyDefinition.Name == "THP_Hookup")
    next(q for q in pset.HasProperties if q.Name == "POC").NominalValue.wrappedValue = "NOT-THE-POC"
    f.write(str(p))
    assert ifc_io.port_connectivity(p)["mismatches"] == [hk.Name]


def test_ifc_passes_schema_and_express_rules(ifc_path):
    import ifcopenshell.validate
    f = ifcopenshell.open(str(ifc_path))
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    assert log.statements == []
    # self-check: the validator must flag a USERDEFINED derived unit without its name
    next(u for u in f.by_type("IfcDerivedUnit") if u.UnitType == "USERDEFINED").UserDefinedType = None
    log2 = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log2, express_rules=True)
    assert log2.statements
