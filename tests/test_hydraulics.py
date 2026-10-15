import math

import pytest

from hookup_planner import engineering as E
from hookup_planner import hydraulics as H

R = 8.31446261815324
RHO_AIR = 101325 * 0.0289647 / (R * 293.15)      # ambient air, 20 degC, 101.325 kPa


def colebrook(re, rel):
    """Independent reference: Colebrook-White solved by fixed-point iteration."""
    x = 0.02 ** -0.5
    for _ in range(200):
        x = -2.0 * math.log10(rel / 3.7 + 2.51 * x / re)
    return 1.0 / (x * x)


def test_laminar_friction_factor_is_64_over_re():
    assert H.friction_factor(1000.0, 1e-3) == pytest.approx(0.064, rel=1e-12)
    assert H.friction_factor(2299.0, 0.0) == pytest.approx(64 / 2299.0, rel=1e-12)
    assert H.regime(2299.0) == "laminar"
    assert H.regime(2300.0) == "transition"
    assert H.regime(4999.0) == "transition"
    assert H.regime(5000.0) == "turbulent"


@pytest.mark.parametrize("re,rel", [(8.0e3, 3e-4), (6.3e4, 1.7e-5), (2.4e6, 2.2e-3)])
def test_swamee_jain_close_to_colebrook(re, rel):
    f = H.friction_factor(re, rel)
    assert f == pytest.approx(0.25 / math.log10(rel / 3.7 + 5.74 / re ** 0.9) ** 2, rel=1e-12)
    assert f == pytest.approx(colebrook(re, rel), rel=0.02)


def test_turbulent_branch_used_from_2300():
    f = H.friction_factor(2300.0, 1e-4)
    assert f != pytest.approx(64 / 2300.0, rel=1e-3)


def test_darcy_weisbach_water_hand_calculation():
    # 30 L/min of water in a 20 mm bore, 17 m, 3 elbows + branch tee + ball valve, 4.3 m rise
    q = 30 / 60000
    d = 0.02
    v = q / (math.pi * d * d / 4)
    rho, mu = 998.21, 1.0016e-3
    re = rho * v * d / mu
    f = 0.25 / math.log10(0.006e-3 / d / 3.7 + 5.74 / re ** 0.9) ** 2
    out = H.line_loss("PCWS", 30.0, d, 17.0, 3, 4.3, 520.0)
    assert out["velocity"] == pytest.approx(v, rel=1e-12)
    assert out["reynolds"] == pytest.approx(re, rel=1e-12)
    assert out["dp_friction_kpa"] == pytest.approx(f * 17 / d * rho * v * v / 2 / 1000, rel=1e-12)
    assert out["dp_minor_kpa"] == pytest.approx((3 * 0.3 + 1.0 + 0.05) * rho * v * v / 2 / 1000, rel=1e-12)
    assert out["dp_static_kpa"] == pytest.approx((rho - RHO_AIR) * 9.80665 * 4.3 / 1000, rel=1e-12)
    assert out["dp_total_kpa"] == pytest.approx(out["dp_friction_kpa"] + out["dp_minor_kpa"] + out["dp_static_kpa"])


def test_static_term_uses_density_difference_to_ambient_air():
    assert E.RHO_AIR_AMBIENT == pytest.approx(RHO_AIR, rel=1e-12)
    assert RHO_AIR == pytest.approx(1.2041, abs=1e-4)
    # room-temperature exhaust: fluid and ambient air almost equal -> static term ~ 0
    ex = H.line_loss("AEX", 900.0, 0.25, 6.0, 2, -4.8, -1.2)
    rho_ex = (101.325 - 1.2) * 1000 * 0.0289647 / (R * 293.15)
    assert ex["dp_static_kpa"] == pytest.approx((rho_ex - RHO_AIR) * 9.80665 * -4.8 / 1000, rel=1e-9)
    assert abs(ex["dp_static_kpa"]) < 1e-3
    assert ex["dp_total_kpa"] > 0          # friction + fittings, no spurious "gain" from the air column
    # compressed gas: the static term is (rho - rho_air) g dz, about 13 % below rho g dz at 700 kPa g
    cda = H.line_loss("CDA", 20.0, 0.0157, 10.0, 3, 4.8, 700.0)
    rho = H.density("CDA", 700.0)
    assert cda["dp_static_kpa"] == pytest.approx((rho - RHO_AIR) * 9.80665 * 4.8 / 1000, rel=1e-12)
    assert 0.12 < 1 - cda["dp_static_kpa"] / (rho * 9.80665 * 4.8 / 1000) < 0.14


def test_fittings_per_kind():
    gas = H.line_loss("N2", 30.0, 0.0157, 8.0, 2, 4.8, 700.0)
    rho = H.density("N2", 700.0)
    v = H.actual_flow_m3s("N2", 30.0, 700.0) / E.area(0.0157)
    assert gas["dp_minor_kpa"] == pytest.approx((2 * 0.3 + 1.05) * rho * v * v / 2 / 1000, rel=1e-12)
    duct = H.line_loss("GEX", 900.0, 0.25, 8.0, 4, -4.8, -1.2)
    v = 0.25 / E.area(0.25)
    assert duct["dp_minor_kpa"] == pytest.approx((4 * 0.3 + 1.0) * H.density("GEX", -1.2) * v * v / 2 / 1000,
                                                 rel=1e-12)


def test_gas_flow_and_density_at_line_pressure():
    q = H.actual_flow_m3s("N2", 90.0, 650.0)
    assert q == pytest.approx(90 / 3600 * 101.325 / 751.325 * 293.15 / 288.15, rel=1e-12)
    rho = H.density("N2", 650.0)
    assert rho == pytest.approx(751325 * 0.028014 / (R * 293.15), rel=1e-12)
    assert H.density("CDA", 0.0) == pytest.approx(101325 * 0.0289647 / (R * 293.15), rel=1e-12)
    assert H.actual_flow_m3s("AEX", 720.0, -1.2) == pytest.approx(0.2, rel=1e-12)
    assert H.actual_flow_m3s("UPW", 42.0, 400.0) == pytest.approx(0.0007, rel=1e-12)


def test_n2_viscosity_interpolated_to_20_degc():
    assert E.FLUIDS["n2"]["mu"] == pytest.approx(16.96e-6 + (293.15 - 280) / 20 * (17.89e-6 - 16.96e-6), rel=1e-12)
    assert E.FLUIDS["n2"]["mu"] == pytest.approx(17.5715e-6, rel=1e-5)


def test_available_pressure_by_role():
    assert H.available_dp_kpa("PCWS", 520.0, 415.0) == pytest.approx(105.0)
    assert H.available_dp_kpa("PCWR", 150.0, 235.0) == pytest.approx(85.0)
    assert H.available_dp_kpa("SEX", -1.2, -0.35) == pytest.approx(0.85)


def test_pcw_loop_differential():
    from hookup_planner.model import tool_side_pressure
    # outlet = supply header 520 - supply loss 75 - tool drop 160 = 285; return may use 285 - 150
    assert H.pcw_outlet_kpa_g(520.0, 75.0, 160.0) == pytest.approx(285.0)
    assert tool_side_pressure("PCWR", 160.0, (520.0, 75.0)) == pytest.approx(285.0)
    assert tool_side_pressure("PCWR", 160.0, None) is None
    assert tool_side_pressure("PCWS", 415.0, (520.0, 75.0)) == 415.0
    ok = H.evaluate_size("PCWR", E.size_by_label("PCWR", "NPS 3/4"), 40.0, 12.0, 3, -4.8, 150.0, 285.0)
    assert ok["available_dp_kpa"] == pytest.approx(135.0) and ok["pressure_ok"]
    # a large tool drop leaves the return less than its own loss: the loop fails
    tight = H.pcw_outlet_kpa_g(520.0, 136.0, 280.0)
    bad = H.evaluate_size("PCWR", E.size_by_label("PCWR", "NPS 1/2"), 40.0, 30.0, 6, -4.8, 150.0, tight)
    assert bad["available_dp_kpa"] == pytest.approx(-46.0)
    assert not bad["pressure_ok"]


def test_static_head_sign_follows_flow_direction():
    from hookup_planner.model import dz_flow
    assert dz_flow("UPW", 3.0) == pytest.approx(3.6)
    assert dz_flow("PCWR", 1.8) == pytest.approx(-4.8)
    assert dz_flow("GEX", 3.6) == pytest.approx(-3.0)


def test_min_velocity_size_is_smallest_under_limit():
    s = H.min_size_velocity("PCWS", 63.0, 520.0)
    v = 63 / 60000 / E.area(s["id"])
    assert v <= 2.5
    smaller = E.PIPE_SIZES[E.size_index("PCWS", s["label"]) - 1]
    assert 63 / 60000 / E.area(smaller["id"]) > 2.5
    # 100 kVA at 400 V: 144.3 A; x 1.25 = 180.4 A -> 200 A breaker
    assert H.min_size_velocity("PWR", 100.0, 0.0)["label"] == "200 A"
    assert H.min_size_velocity("PWR", 69.0, 0.0)["label"] == "125 A"
    assert H.min_size_velocity("PWR", 70.0, 0.0)["label"] == "160 A"


def test_pressure_governs_on_a_long_run():
    short = H.select_size("PCWS", 47.0, 9.0, 2, 4.8, 520.0, 450.0)
    long_ = H.select_size("PCWS", 47.0, 61.0, 7, 4.8, 520.0, 450.0)
    assert short["governed_by"] == "velocity"
    assert long_["governed_by"] == "pressure"
    n = E.size_index("PCWS", long_["size"]["label"])
    assert n > E.size_index("PCWS", short["size"]["label"])
    below = E.PIPE_SIZES[n - 1]
    ev = H.evaluate_size("PCWS", below, 47.0, 61.0, 7, 4.8, 520.0, 450.0)
    assert ev["velocity_ok"] and not ev["pressure_ok"]
    assert long_["eval"]["dp_total_kpa"] <= 70.0


def test_gas_validity_can_govern_and_is_labelled_so():
    sel = H.select_size("N2", 17.0, 150.0, 4, 4.8, 700.0, 0.0)
    assert sel["governed_by"] == "gas validity"
    assert sel["size"]["label"] == "OD 3/4 in"
    below = H.evaluate_size("N2", E.size_by_label("N2", "OD 1/2 in"), 17.0, 150.0, 4, 4.8, 700.0, 0.0)
    assert below["velocity_ok"] and below["pressure_ok"] and not below["valid_model"]


def test_no_size_when_pressure_cannot_be_met():
    res = H.select_size("PCWS", 47.0, 20.0, 2, 4.8, 520.0, 519.0)
    assert res["size"] is None and res["governed_by"] == "none"


def test_gas_model_validity_flag():
    ok = H.evaluate_size("N2", E.size_by_label("N2", "OD 3/4 in"), 40.0, 12.0, 3, 4.8, 650.0, 600.0)
    assert ok["valid_model"]
    bad = H.evaluate_size("N2", E.size_by_label("N2", "OD 1/2 in"), 100.0, 40.0, 3, 4.8, 650.0, -100.0)
    assert bad["dp_total_kpa"] >= 0.1 * 751.325
    assert not bad["valid_model"] and not bad["ok"]


def test_exhaust_design_velocity_is_1500_fpm_inside_published_range():
    assert E.SYSTEMS["GEX"]["v_max"] == pytest.approx(7.62, rel=1e-12)
    lo, hi = E.EXHAUST_RANGE_V
    assert lo == pytest.approx(5.08, rel=1e-12) and hi == pytest.approx(10.16, rel=1e-12)
    s = H.min_size_velocity("GEX", 900.0, -1.2)
    assert s["label"] == "D250"   # D200 would run at 7.96 m/s


def test_pipe_and_tube_catalogue_inner_diameters():
    assert E.size_by_label("PCWS", "NPS 1")["id"] == pytest.approx(0.02786, rel=1e-12)
    assert E.size_by_label("UPW", "NPS 2 1/2")["id"] == pytest.approx(0.06693, rel=1e-12)
    # OD tubing: 3/4 in x 0.065 in wall -> 0.62 in bore
    assert E.size_by_label("CDA", "OD 3/4 in")["id"] == pytest.approx(0.62 * 0.0254, rel=1e-12)
    assert E.size_by_label("N2", "OD 1/2 in")["od"] == pytest.approx(0.0127, rel=1e-12)
    assert E.SYSTEMS["CDA"]["material"] == "ss_ep_tube" and E.ROUGHNESS_M["ss_ep_tube"] == pytest.approx(0.0008e-3)


def test_breaker_sizing_uses_amps_and_continuous_factor():
    assert E.kva_to_amps(100.0) == pytest.approx(100000 / (math.sqrt(3) * 400), rel=1e-12)
    assert not E.breaker_ok(180.0, 100.0) and E.breaker_ok(181.0, 100.0)
    assert E.breaker_kva(200.0) == pytest.approx(200 / 1.25 * math.sqrt(3) * 400 / 1000, rel=1e-12)
    s160 = E.size_by_label("PWR", "160 A")
    assert H.evaluate_size("PWR", s160, 88.0, 10.0, 2, 4.8, 0.0, 0.0)["ok"]
    assert not H.evaluate_size("PWR", s160, 89.0, 10.0, 2, 4.8, 0.0, 0.0)["ok"]
    sel = H.select_size("PWR", 71.0, 10.0, 2, 4.8, 0.0, 0.0)
    assert sel["size"]["label"] == "160 A" and sel["governed_by"] == "rating"
    assert sel["eval"]["design_current_a"] == pytest.approx(71000 / (math.sqrt(3) * 400), rel=1e-12)
