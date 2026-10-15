"""Pressure drop (Darcy-Weisbach + Swamee-Jain), velocity limits and line sizing.

Units: flow in the system's flow unit (L/min, Sm3/h, m3/h, kVA), pressure in kPa gauge,
lengths in metres.
"""
from __future__ import annotations

import math

from . import engineering as E


def abs_pressure_kpa(p_kpa_g: float) -> float:
    return E.P_ATM_KPA + p_kpa_g


def actual_flow_m3s(system: str, flow: float, line_p_kpa_g: float) -> float:
    kind = E.SYSTEMS[system]["kind"]
    if kind == "liquid":
        return flow / 60000.0
    if kind == "gas":
        # standard m3 (15 degC, 101.325 kPa) -> actual m3 at line pressure, ideal gas law
        return flow / 3600.0 * (E.P_ATM_KPA / abs_pressure_kpa(line_p_kpa_g)) * (E.T_OP_K / E.T_STD_K)
    if kind == "exhaust":
        return flow / 3600.0
    raise ValueError(f"{system} carries no fluid")


def density(system: str, line_p_kpa_g: float) -> float:
    fl = E.FLUIDS[E.SYSTEMS[system]["fluid"]]
    if fl["rho"] is not None:
        return fl["rho"]
    return abs_pressure_kpa(line_p_kpa_g) * 1000.0 * fl["molar_mass"] / (E.R_GAS * E.T_OP_K)


def friction_factor(re: float, rel_rough: float) -> float:
    """Darcy friction factor: 64/Re when laminar, Swamee-Jain otherwise (SRC_FRICTION_FORMULAE)."""
    if re <= 0:
        return 0.0
    if re < E.RE_LAMINAR_MAX:
        return 64.0 / re
    return 0.25 / math.log10(rel_rough / 3.7 + 5.74 / re ** 0.9) ** 2


def regime(re: float) -> str:
    if re < E.RE_LAMINAR_MAX:
        return "laminar"
    if re < E.RE_SWAMEE_JAIN_MIN:
        return "transition"   # Swamee-Jain used outside its stated range; flagged in output
    return "turbulent"


def line_loss(system: str, flow: float, inner_d: float, length: float, n_elbows: int,
              dz_flow: float, line_p_kpa_g: float) -> dict:
    """Loss of gauge pressure along a hookup in the flow direction.

    dz_flow = elevation(outlet) - elevation(inlet) in the flow direction.  The static term
    uses the density difference between the fluid and the ambient air, because gauge
    pressure is measured against the ambient pressure at the same height, which itself
    falls by rho_air g dz (SRC_HYDROSTATIC, SRC_GAUGE_PRESSURE, SRC_STACK_EFFECT).  For
    room-temperature exhaust the two densities are almost equal and the term is ~0.
    """
    sysd = E.SYSTEMS[system]
    fl = E.FLUIDS[sysd["fluid"]]
    q = actual_flow_m3s(system, flow, line_p_kpa_g)
    rho = density(system, line_p_kpa_g)
    v = q / E.area(inner_d)
    re = rho * v * inner_d / fl["mu"]
    f = friction_factor(re, E.ROUGHNESS_M[sysd["material"]] / inner_d)
    dyn = rho * v * v / 2.0
    k_fit = E.FITTINGS_K[sysd["kind"]]
    dp_fric = f * length / inner_d * dyn / 1000.0                    # SRC_DARCY
    dp_minor = (n_elbows * E.ELBOW_K + k_fit) * dyn / 1000.0         # SRC_MINOR_LOSS
    dp_static = (rho - E.RHO_AIR_AMBIENT) * E.G * dz_flow / 1000.0   # SRC_HYDROSTATIC, SRC_STACK_EFFECT
    return {"velocity": v, "reynolds": re, "friction_factor": f, "regime": regime(re),
            "dp_friction_kpa": dp_fric, "dp_minor_kpa": dp_minor, "dp_static_kpa": dp_static,
            "dp_total_kpa": dp_fric + dp_minor + dp_static}


def pcw_outlet_kpa_g(supply_header_p: float, supply_dp: float, tool_dp: float) -> float:
    """PCW pressure leaving the tool: supply header - supply hookup loss - tool internal drop."""
    return supply_header_p - supply_dp - tool_dp


def available_dp_kpa(system: str, header_p_kpa_g: float, tool_p_kpa_g: float) -> float:
    """Pressure the hookup may consume.

    supply : header pressure minus the tool's minimum inlet pressure
    return : pressure at the tool outlet (see pcw_outlet_kpa_g) minus the return-header pressure
    exhaust: tool's required port static pressure (negative) minus the header static pressure
    """
    role = E.SYSTEMS[system]["role"]
    if role == "supply":
        return header_p_kpa_g - tool_p_kpa_g
    return tool_p_kpa_g - header_p_kpa_g


def evaluate_size(system: str, size: dict, flow: float, length: float, n_elbows: int,
                  dz_flow: float, header_p_kpa_g: float, tool_p_kpa_g: float) -> dict:
    """Velocity, pressure and validity checks of one candidate size.

    ``tool_p_kpa_g`` is the pressure condition at the tool end: minimum inlet pressure
    (supply), outlet pressure (PCW return, from pcw_outlet_kpa_g) or required port static
    pressure (exhaust).
    """
    sysd = E.SYSTEMS[system]
    if sysd["kind"] == "power":
        ok = E.breaker_ok(size["amps"], flow)
        return {"ok": ok, "velocity_ok": True, "pressure_ok": True, "valid_model": True,
                "velocity": None, "dp_total_kpa": None, "available_dp_kpa": None, "regime": None,
                "capacity_ok": ok, "design_current_a": E.kva_to_amps(flow)}
    loss = line_loss(system, flow, size["id"], length, n_elbows, dz_flow, header_p_kpa_g)
    avail = available_dp_kpa(system, header_p_kpa_g, tool_p_kpa_g)
    v_ok = loss["velocity"] <= sysd["v_max"]
    p_ok = loss["dp_total_kpa"] <= avail
    valid = True
    if sysd["kind"] in ("gas", "exhaust"):
        valid = abs(loss["dp_total_kpa"]) < E.GAS_DP_FRACTION_MAX * abs_pressure_kpa(header_p_kpa_g)
    return {"ok": v_ok and p_ok and valid, "velocity_ok": v_ok, "pressure_ok": p_ok, "valid_model": valid,
            "velocity": loss["velocity"], "dp_total_kpa": loss["dp_total_kpa"], "available_dp_kpa": avail,
            "regime": loss["regime"], "capacity_ok": True, "dp_friction_kpa": loss["dp_friction_kpa"],
            "dp_minor_kpa": loss["dp_minor_kpa"], "dp_static_kpa": loss["dp_static_kpa"]}


def min_size_velocity(system: str, flow: float, header_p_kpa_g: float) -> dict | None:
    """Smallest catalogue size meeting the velocity limit (or the breaker rule for power)."""
    for s in E.sizes_for(system):
        if E.SYSTEMS[system]["kind"] == "power":
            if E.breaker_ok(s["amps"], flow):
                return s
            continue
        v = actual_flow_m3s(system, flow, header_p_kpa_g) / E.area(s["id"])
        if v <= E.SYSTEMS[system]["v_max"]:
            return s
    return None


def select_size(system: str, flow: float, length: float, n_elbows: int, dz_flow: float,
                header_p_kpa_g: float, tool_p_kpa_g: float) -> dict:
    """Smallest catalogue size passing every check; reports which check governed the choice.

    governed_by: ``velocity`` (the velocity-limit size passes), ``pressure`` (the next smaller
    size fails the pressure budget), ``gas validity`` (it passes the budget but its loss is
    >= 10 % of the inlet absolute pressure), ``rating`` (power).
    """
    sizes = E.sizes_for(system)
    vel_only = min_size_velocity(system, flow, header_p_kpa_g)
    for n, s in enumerate(sizes):
        ev = evaluate_size(system, s, flow, length, n_elbows, dz_flow, header_p_kpa_g, tool_p_kpa_g)
        if not ev["ok"]:
            continue
        if E.SYSTEMS[system]["kind"] == "power":
            governed = "rating"
        elif vel_only is not None and s["label"] == vel_only["label"]:
            governed = "velocity"
        else:
            below = evaluate_size(system, sizes[n - 1], flow, length, n_elbows, dz_flow, header_p_kpa_g,
                                  tool_p_kpa_g)
            governed = "pressure" if not below["pressure_ok"] else "gas validity"
        return {"size": s, "eval": ev, "governed_by": governed}
    return {"size": None, "eval": None, "governed_by": "none"}
