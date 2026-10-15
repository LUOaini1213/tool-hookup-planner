"""Engineering constants and the utility-system catalogue.

Every constant that comes from an outside reference carries the key of its entry in
docs/sources.md (``SRC_*`` comments).  Values marked ILLUSTRATIVE are modelling choices
of this project, not engineering rules, and are listed as such in the README.
"""
from __future__ import annotations

import math

# --- physical constants -------------------------------------------------------------
G = 9.80665                      # m/s^2, standard gravity                  SRC_GRAVITY
R_GAS = 8.31446261815324         # J/(mol K), molar gas constant           SRC_GAS_CONSTANT
P_ATM_KPA = 101.325              # kPa, reference pressure of a standard m3 SRC_STD_M3
T_STD_K = 288.15                 # K (15 degC), reference temp of a standard m3 SRC_STD_M3
T_OP_K = 293.15                  # K (20 degC) operating temperature -- ILLUSTRATIVE assumption
FT_PER_MIN_TO_M_PER_S = 0.3048 / 60.0   # 1 ft = 0.3048 m exactly            SRC_FOOT
INCH_M = 0.0254                  # 1 in = 25.4 mm exactly                   SRC_INCH

# --- fluid properties ---------------------------------------------------------------
M_AIR = 28.9647e-3               # kg/mol, dry air                          SRC_AIR_MOLAR_MASS
# Nitrogen viscosity at 1 bar, tabulated at 280 K and 300 K (SRC_N2_VISCOSITY); the value at
# the operating temperature is linearly interpolated between the two rows.
N2_MU_280K, N2_MU_300K = 16.96e-6, 17.89e-6
N2_MU_OP = N2_MU_280K + (T_OP_K - 280.0) / 20.0 * (N2_MU_300K - N2_MU_280K)
FLUIDS = {
    # density only for liquids; gases get density from the ideal-gas law at line pressure
    "water": {"rho": 998.21, "mu": 1.0016e-3, "molar_mass": None},     # SRC_WATER_DENSITY, SRC_WATER_VISCOSITY
    "air": {"rho": None, "mu": 18.13e-6, "molar_mass": M_AIR},          # SRC_AIR_VISCOSITY, SRC_AIR_MOLAR_MASS
    "n2": {"rho": None, "mu": N2_MU_OP, "molar_mass": 2 * 14.007e-3},   # SRC_N2_VISCOSITY, SRC_N_ATOMIC_WEIGHT
}
# Ambient (room) air around the hookups, at the reference pressure and the operating
# temperature.  Gauge pressure is referenced to the ambient pressure at the same height, so
# a vertical rise changes the gauge pressure by (rho_fluid - rho_ambient) g dz
# (SRC_GAUGE_PRESSURE, SRC_STACK_EFFECT).
RHO_AIR_AMBIENT = P_ATM_KPA * 1000.0 * M_AIR / (R_GAS * T_OP_K)

# --- friction and fittings ------------------------------------------------------------
RE_LAMINAR_MAX = 2300.0          # laminar below this Reynolds number        SRC_FRICTION_FORMULAE
RE_SWAMEE_JAIN_MIN = 5000.0      # lower validity bound of Swamee-Jain       SRC_FRICTION_FORMULAE
ELBOW_K = 0.3                    # 90 deg elbow, flanged regular             SRC_MINOR_LOSS
TEE_BRANCH_K = 1.0               # tee, flanged, dividing branched flow      SRC_MINOR_LOSS
BALL_VALVE_K = 0.05              # ball valve, fully open (POC isolation)    SRC_MINOR_LOSS
GAS_DP_FRACTION_MAX = 0.10       # incompressible Darcy valid if dp < 10 % of inlet abs. pressure  SRC_COMPRESSIBLE_DARCY

# absolute roughness, metres (value used per row is stated in docs/sources.md)  SRC_ROUGHNESS
ROUGHNESS_M = {
    "stainless": 0.006e-3,      # bead blasted / turned, upper end of 0.001-0.006 mm
    "ss_ep_tube": 0.0008e-3,    # electropolished, upper end of 0.0001-0.0008 mm
    "plastic": 0.007e-3,        # PVC/PE smooth plastic, upper end of 0.0015-0.007 mm
    "galvanized": 0.15e-3,      # single value
    "copper": 0.0,              # power cable: no hydraulics
}

# --- size catalogues -----------------------------------------------------------------
# NPS outside diameter and Schedule 10S wall, mm                              SRC_NPS
NPS_10S = [
    ("1/2", 21.34, 2.11),
    ("3/4", 26.67, 2.11),
    ("1", 33.40, 2.77),
    ("1 1/4", 42.16, 2.77),
    ("1 1/2", 48.26, 2.77),
    ("2", 60.33, 2.77),
    ("2 1/2", 73.03, 3.05),
    ("3", 88.90, 3.05),
    ("4", 114.30, 3.05),
    ("6", 168.28, 3.40),
]
PIPE_SIZES = [{"label": f"NPS {lab}", "od": od / 1000.0, "id": (od - 2 * wall) / 1000.0}
              for lab, od, wall in NPS_10S]
# OD-sized stainless tubing for the gas hookups: outside diameter and wall in inches
# (0.065 in wall for 1/2 to 2 in OD)                                         SRC_TUBE
TUBE_OD_IN = [("1/2", 0.5, 0.065), ("3/4", 0.75, 0.065), ("1", 1.0, 0.065), ("1 1/2", 1.5, 0.065),
              ("2", 2.0, 0.065)]
TUBE_SIZES = [{"label": f"OD {lab} in", "od": od * INCH_M, "id": (od - 2 * wall) * INCH_M}
              for lab, od, wall in TUBE_OD_IN]
# round duct diameters -- ILLUSTRATIVE catalogue (no external rule)
DUCT_SIZES = [{"label": f"D{d}", "od": d / 1000.0, "id": d / 1000.0} for d in range(100, 650, 50)]

# --- power -----------------------------------------------------------------------------
V_LL = 400.0                     # V line-to-line, 230/400 V three-phase     SRC_THREE_PHASE (choice ILLUSTRATIVE)
CONTINUOUS_LOAD_FACTOR = 1.25    # breaker rating >= 125 % of a continuous load   SRC_NEC_CONTINUOUS
# breaker / feeder ratings in A -- ILLUSTRATIVE catalogue
POWER_SIZES = [{"label": f"{a} A", "od": 0.06, "id": None, "amps": float(a)} for a in (32, 63, 100, 125, 160, 200, 250, 320, 400)]


def kva_to_amps(kva: float) -> float:
    """Line current of a balanced three-phase load: S = sqrt(3) V_LL I (SRC_THREE_PHASE)."""
    return kva * 1000.0 / (math.sqrt(3.0) * V_LL)


def breaker_kva(amps: float) -> float:
    """Largest continuous load (kVA) a breaker of ``amps`` may feed under the 125 % rule."""
    return amps / CONTINUOUS_LOAD_FACTOR * math.sqrt(3.0) * V_LL / 1000.0


def breaker_ok(amps: float, kva: float) -> bool:
    return amps >= CONTINUOUS_LOAD_FACTOR * kva_to_amps(kva) - 1e-9


# --- utility systems -----------------------------------------------------------------
# role: supply = header -> tool, return/exhaust = tool -> header.
EXHAUST_DESIGN_V = 1500 * FT_PER_MIN_TO_M_PER_S   # design velocity inside 1000-2000 fpm  SRC_DUCT_VELOCITY
EXHAUST_RANGE_V = (1000 * FT_PER_MIN_TO_M_PER_S, 2000 * FT_PER_MIN_TO_M_PER_S)  # SRC_DUCT_VELOCITY
SYSTEMS = {
    "PCWS": {"name": "Process cooling water supply", "kind": "liquid", "role": "supply", "fluid": "water",
             "flow_unit": "L/min", "material": "stainless", "v_max": 2.5, "v_src": "SRC_WATER_VELOCITY"},
    "PCWR": {"name": "Process cooling water return", "kind": "liquid", "role": "return", "fluid": "water",
             "flow_unit": "L/min", "material": "stainless", "v_max": 2.5, "v_src": "SRC_WATER_VELOCITY"},
    "UPW": {"name": "Ultrapure water", "kind": "liquid", "role": "supply", "fluid": "water",
            "flow_unit": "L/min", "material": "plastic", "v_max": 3.0, "v_src": "SRC_WATER_VELOCITY"},
    "CDA": {"name": "Clean dry air", "kind": "gas", "role": "supply", "fluid": "air",
            "flow_unit": "Sm3/h", "material": "ss_ep_tube", "v_max": 9.0, "v_src": "SRC_CDA_VELOCITY"},
    "N2": {"name": "Nitrogen", "kind": "gas", "role": "supply", "fluid": "n2",
           "flow_unit": "Sm3/h", "material": "ss_ep_tube", "v_max": 9.0, "v_src": "SRC_CDA_VELOCITY"},
    "GEX": {"name": "General exhaust", "kind": "exhaust", "role": "exhaust", "fluid": "air",
            "flow_unit": "m3/h", "material": "galvanized", "v_max": EXHAUST_DESIGN_V, "v_src": "SRC_DUCT_VELOCITY"},
    "AEX": {"name": "Acid exhaust", "kind": "exhaust", "role": "exhaust", "fluid": "air",
            "flow_unit": "m3/h", "material": "plastic", "v_max": EXHAUST_DESIGN_V, "v_src": "SRC_DUCT_VELOCITY"},
    "SEX": {"name": "Solvent exhaust", "kind": "exhaust", "role": "exhaust", "fluid": "air",
            "flow_unit": "m3/h", "material": "stainless", "v_max": EXHAUST_DESIGN_V, "v_src": "SRC_DUCT_VELOCITY"},
    "PWR": {"name": "Process power", "kind": "power", "role": "supply", "fluid": None,
            "flow_unit": "kVA", "material": "copper", "v_max": None, "v_src": None},
}
SYSTEM_ORDER = ["PCWS", "PCWR", "UPW", "CDA", "N2", "GEX", "AEX", "SEX", "PWR"]
# PCW supply and return of one tool form a loop and are planned as a pair.
PCW_PAIR = ("PCWS", "PCWR")

# Coincidence factor (= 1 / diversity factor, SRC_COINCIDENCE) applied to summed peak loads.
# No public numeric value for fab tool loads was found, so no diversity credit is taken.
COINCIDENCE_FACTOR = {s: 1.0 for s in SYSTEM_ORDER}

# Fittings counted on every hookup besides one elbow per route bend: the branch take-off
# from the header (dividing branch tee) for every fluid hookup, and an open isolation ball
# valve at the POC for pipe and tube hookups.  Flex connectors, reducers, dampers, filters
# and regulators are not modelled (see README limitations).
FITTINGS_K = {"liquid": TEE_BRANCH_K + BALL_VALVE_K, "gas": TEE_BRANCH_K + BALL_VALVE_K,
              "exhaust": TEE_BRANCH_K}

# --- modelling choices (ILLUSTRATIVE) -------------------------------------------------
CLEARANCE_M = 0.05        # minimum surface-to-surface gap used by the clash check
FAB_FLOOR_Z = 6.6         # top of fab-level floor; tool connection points sit here


def sizes_for(system: str) -> list[dict]:
    kind = SYSTEMS[system]["kind"]
    if kind == "exhaust":
        return DUCT_SIZES
    if kind == "power":
        return POWER_SIZES
    if kind == "gas":
        return TUBE_SIZES
    return PIPE_SIZES


def size_by_label(system: str, label: str) -> dict:
    for s in sizes_for(system):
        if s["label"] == label:
            return s
    raise KeyError(f"{system}: unknown size {label!r}")


def size_index(system: str, label: str) -> int:
    return [s["label"] for s in sizes_for(system)].index(label)


def area(d: float) -> float:
    return math.pi * d * d / 4.0
