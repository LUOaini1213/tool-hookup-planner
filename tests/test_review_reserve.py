"""Invalid reserve values must not turn an overloaded proposal into a clean review."""
import copy
import json
import math

import pytest

from hookup_planner import cli, db
from hookup_planner.capacity import capacity_check
from hookup_planner.engineering import COINCIDENCE_FACTOR
from hookup_planner.model import header_loads
from hookup_planner.review import review


@pytest.fixture(scope="module")
def overloaded(small_plan):
    site = copy.deepcopy(small_plan["site"])
    proposal = [{key: h[key] for key in ("id", "tool", "system", "poc", "size", "points")}
                for h in small_plan["hookups"]]
    pocs = {p["id"]: p for p in site["pocs"]}
    header_id = pocs[proposal[0]["poc"]]["header"]
    header = next(h for h in site["headers"] if h["id"] == header_id)
    demands = {(d["tool"], d["system"]): d["flow"] for d in site["demands"]}
    new_load = sum(demands[h["tool"], h["system"]] * COINCIDENCE_FACTOR[h["system"]]
                   for h in proposal if pocs[h["poc"]]["header"] == header_id)
    header["capacity"] = header_loads(site)[header_id] + new_load - 0.5
    upgrades = {key: value for key, value in small_plan["assignment"]["milp"]["upgrades"].items()
                if key != header_id}
    return site, proposal, upgrades


@pytest.mark.parametrize("reserve", [float("nan"), float("inf"), -float("inf"), -0.01, 1, 1.1, True, False])
def test_review_rejects_invalid_reserve_instead_of_approving_overload(overloaded, reserve):
    site, proposal, upgrades = overloaded
    assert any(i["code"] == "HEADER_OVER_CAPACITY" for i in review(site, proposal, upgrades))
    with pytest.raises(ValueError, match=r"reserve.*\[0, 1\)"):
        review(site, proposal, upgrades, reserve=reserve)


@pytest.mark.parametrize("reserve", [None, "0.1", [], {}])
def test_review_rejects_nonnumeric_reserve_before_reading_site(reserve):
    with pytest.raises(ValueError, match="reserve"):
        review({}, [], reserve=reserve)


@pytest.mark.parametrize("reserve", [0, 0.0, 0.1, math.nextafter(1.0, 0.0)])
def test_valid_reserve_preserves_capacity_findings_without_mutating_inputs(overloaded, reserve):
    site, proposal, upgrades = overloaded
    before = json.dumps([site, proposal, upgrades], sort_keys=True, allow_nan=False)
    issues = review(site, proposal, upgrades, reserve=reserve)
    assert any(i["code"] == "HEADER_OVER_CAPACITY" for i in issues)
    assert json.dumps([site, proposal, upgrades], sort_keys=True, allow_nan=False) == before


@pytest.mark.parametrize("reserve", [True, False])
def test_capacity_and_review_share_the_numeric_fraction_contract(small_site, reserve):
    with pytest.raises(ValueError, match="reserve"):
        capacity_check(small_site, reserve=reserve)


@pytest.mark.parametrize("command", ["review", "capacity"])
@pytest.mark.parametrize("reserve", ["nan", "inf", "-inf", "-0.1", "1", "true"])
def test_cli_rejects_bad_reserve_before_opening_any_input(tmp_path, capsys, command, reserve):
    database = tmp_path / "must-not-be-created.db"
    args = [command]
    if command == "review":
        args.append(str(tmp_path / "missing-proposal.json"))
    args += ["--db", str(database), f"--reserve={reserve}"]
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "--reserve" in stderr and "Traceback" not in stderr
    assert not database.exists()


def test_cli_valid_and_nan_reserves_on_the_same_overloaded_database(overloaded, tmp_path, capsys):
    site, proposal, upgrades = overloaded
    database = tmp_path / "synthetic.db"
    connection = db.connect(database)
    try:
        db.write_site(connection, site)
    finally:
        connection.close()
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps({"hookups": proposal, "upgrades": upgrades}), encoding="utf-8")
    original_database = database.read_bytes()
    original_proposal = path.read_bytes()
    args = ["review", str(path), "--db", str(database)]
    assert cli.main([*args, "--reserve=0"]) == 1
    assert "HEADER_OVER_CAPACITY" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        cli.main([*args, "--reserve=nan"])
    assert exc.value.code == 2
    assert "--reserve" in capsys.readouterr().err
    assert database.read_bytes() == original_database
    assert path.read_bytes() == original_proposal
