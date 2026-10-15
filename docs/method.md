# Method

All data in this repository are synthetic and illustrative. This page explains what each
step computes and which simplifications it makes; rules and constants are cited in
[sources.md](sources.md).

Terms: the sub-fab *headers* (mains) run along the corridors; *process lateral* (PLS) work
extends them to points of connection (here: header capacity steps and new POCs); a
*hookup* runs from a POC to the tool's connection point; after the hookups are tested,
utilities are turned on and the tool is handed to the vendor for start-up.

## 1. Data model

A *site* is one plain dictionary that is written to IFC, read back from IFC, and stored in
SQLite (`src/hookup_planner/schema.sql`):

| Table | Content |
|---|---|
| `utility_system` | PCWS / PCWR (process cooling water supply / return), UPW, CDA, N2, GEX / AEX / SEX (general / acid / solvent exhaust), PWR; kind, role (supply, return, exhaust), flow unit, material, velocity limit, coincidence factor |
| `header` | sub-fab main: system, corridor, axis position, outer diameter, design capacity, supply/return pressure or exhaust static pressure, size, cost and duration of one capacity step |
| `poc` | point of connection on a header: position, nominal size, rated flow, status (`free`, `in_use`, `reserved`, `planned`) |
| `structural_column`, `equipment` | obstacles: columns and sub-fab support equipment (boxes) |
| `tool`, `tool_demand` | process tools (existing or new) and, per utility, peak demand, pressure value and the floor penetration (connection point) |
| `hookup`, `route_point` | hookups with status (`planned` → `installed` → `tested` → `released`) and their routed centre-lines |

Views: `v_header_load` (connected load and remaining capacity per header, counting only
installed/tested/released hookups), `v_free_poc`, `v_tool_demand_total`.

Pressure conventions (kPa gauge unless stated): a supply tool states its minimum inlet
pressure; an exhaust port states the static pressure it needs (negative); for the PCW
return the demand record holds the tool's internal pressure drop (kPa) between its supply
and return connections. The pressure a hookup may consume is

* supply: header − minimum inlet pressure;
* exhaust: required port pressure − header;
* PCW return: (supply header − supply hookup loss − tool pressure drop) − return header,
  i.e. the loop must close: supply header − supply loss − tool drop − return loss ≥
  return header.

## 2. Synthetic sub-fab and IFC

`scenario.py` builds a 7 × 4 bay sub-fab (7.2 m bays, 0.5 m columns, 6.0 m clear height,
fab floor at +6.6 m). Wet/gas corridors (PCWS, PCWR, UPW, CDA, N2) and exhaust/power
corridors (AEX, SEX, GEX, PWR busbar) alternate between bay rows; headers run along x at
mid-bay. POCs sit every 3.6 m on each header. Existing tools are hooked up first
(nearest feasible free POC, PCW return on the corridor of the supply, routed with the
same A* router) and their hookups become obstacles. Header capacities are then set to
existing load plus a headroom that is a fixed multiple of the new tools' demand; the
multiples (`headroom_factor`) were chosen so that at least one system runs short and
capacity steps are exercised.

`ifc_io.py` writes IFC4 with IfcOpenShell: IfcGrid and IfcColumn; headers as
IfcPipeSegment / IfcDuctSegment / IfcCableSegment(BUSBARSEGMENT) with IfcSweptDiskSolid
bodies; POCs as IfcValve / IfcDamper / IfcProtectiveDevice; tools and support equipment
as IfcBuildingElementProxy; hookups as segments with swept-disk centre-line geometry;
one IfcDistributionSystem per utility. Connectivity: IfcDistributionPort objects are
nested (IfcRelNests) on headers (one per POC), POCs (header side and hookup side), hookups
(POC end and tool end) and tools (one per utility), and IfcRelConnectsPorts joins
header → POC → hookup → tool, with flow directions SOURCE/SINK following the flow.
Project data live in `THP_*` property sets (not the reserved `Pset_` prefix); quantities
carry measure types and units on the property (kPa as an SI unit with KILO prefix; L/min,
m³/h as derived units built from litre/minute/hour conversion units; Sm³/h and kVA as
named user-defined derived units; m/s; day; the notional currency CU). The header declares
`ViewDefinition [ReferenceView_V1.2]`, author `tool-hookup-planner`, organisation
`illustrative`. GlobalIds are derived from element names (UUID5) and the header timestamp
is fixed, so the same input always produces the same bytes.

Reading back takes positions and sizes from the IFC placements and solids, attributes from
the property sets; the database is populated from the read-back model. The round trip
(seed → IFC → site → SQLite → site) must reproduce the seed exactly, and following the
ports from every hookup and POC must reach the POC, tool and header named in its
property set (`results/roundtrip.json`, `ifc_io.port_connectivity`).

## 3. Capacity check

Per header: usable = capacity × (1 − reserve); remaining = usable − connected load.
Per system: new load = Σ peak demand × coincidence factor (1.0, see sources). A system
whose new load exceeds its remaining capacity is a SHORTFALL; the minimum number of
capacity steps is ⌈shortfall / step⌉. The system view is a lower bound: which headers
actually need the steps is decided by the assignment, because every tool connects to one
specific header.

## 4. POC assignment (MILP)

For each requirement r (tool × utility) the candidate POCs are the free POCs of the same
system whose rating covers the demand, plus *potential new POCs*: new take-off positions
half way between existing POCs, priced at an illustrative fixed cost (how such a branch
is made depends on the utility; the model only prices it). The estimated length of each
pair is take-off stub + obstacle-aware breadth-first distance on the routing lattice +
floor riser.

The MILP (scipy/HiGHS, `mip_rel_gap = 0`) picks one POC per requirement, at most one
requirement per POC position, and integer capacity steps per header:

    minimise   Σ (rate_m · length_rp + new_poc_cost_rp) x_rp + Σ C_h y_h + BIG Σ u_r
    subject to Σ_p x_rp + u_r = 1                 for every requirement r
               Σ_r x_rp ≤ 1                       for every POC position p
               Σ_{p on h} d_r x_rp − step_h y_h ≤ remaining_h   for every header h
               Σ_{p in c} x_sp − Σ_{p in c} x_tp = 0   for every tool's PCW supply s and
                                                       return t, and every corridor c
               x, u ∈ {0,1}, y_h ∈ {0..5}

The pairing rows put a tool's PCW supply and return on the same corridor (or leave both
unserved). A perturbation of 10⁻⁶ × (variable index) makes the optimum unique, so the
result does not depend on how the solver breaks ties. Two checks run every time: with the
capacity and pairing rows removed the MILP must equal `scipy.optimize.linear_sum_assignment`,
and tests compare the MILP with brute-force enumeration on small instances, with and
without pairing. The baseline is a greedy rule (each requirement in list order takes its
cheapest free POC, a PCW return only on its supply's corridor, and adds a capacity step to
that header if it is short). The results also report the unpaired MILP, to show what the
pairing rule costs, and both methods over planning reserves of 0, 2, 5, 10 and 20 %.

## 5. Routing (A*) and sizing

The sub-fab is a 0.6 m lattice (85 × 49 × 11 nodes). For each obstacle the code stores the
surface gap from every node; a node is free for a run of radius r if the gap is at least
r + clearance. Because columns, headers and equipment are centred on lattice lines and
every run is a lattice edge, the closest point of an edge to an obstacle is one of its end
nodes, so checking nodes is enough. Each hookup:

1. rises from its POC (on the header axis) in a straight take-off until clear of its own
   header (the take-off is the only place a run may be close to its own header);
2. is routed by A* (cost = 5 per step + 5 per change of direction, Manhattan heuristic)
   to the node under the tool's floor penetration, entering it from below;
3. rises through the slab to the fab floor (+6.6 m).

Nodes under every tool penetration and above every chosen take-off are reserved so earlier
routes cannot block later ones. Routes are planned one at a time (ducts first, then pipes,
then cables; larger flows first; every PCW supply before any PCW return) and each routed
run becomes an obstacle for the rest.

Sizing uses the routed length and bend count. The loss of gauge pressure along a hookup is

    Δp = f L/D · ρv²/2  +  (0.3 · bends + ξ_fittings) · ρv²/2  +  (ρ − ρ_air) g Δz

with ξ_fittings = 1.0 (branch tee at the take-off) + 0.05 (open ball valve at the POC) for
pipe and tube, 1.0 for ducts, and Δz the rise in the flow direction. The static term uses
the density difference to the ambient air because every pressure is gauge, referenced to
the ambient pressure at the same height; for room-temperature exhaust it is practically
zero. The chosen size is the smallest catalogue size whose velocity is within the limit,
whose loss is within the available pressure (for the PCW return: what the loop leaves
after the supply hookup, which is sized first) and, for gas, whose loss is under 10 % of
the inlet absolute pressure. Water lines use NPS Schedule 10S pipe, CDA/N2 lines OD tubing,
exhaust round ducts. Power feeders take the smallest breaker rated at least 1.25 × the
design current at 400 V three-phase. If the size grows, the hookup is re-routed with the
larger radius. The hookup list records which check governed the size: `velocity`,
`pressure` (the next smaller size fails the pressure budget), `gas validity` (it meets the
budget but breaks the 10 % rule) or `rating` (power).

## 6. Clash detection

Every element is an axis-aligned box (a straight run is a box of zero thickness) inflated
by a radius. The surface gap between two elements is the box-to-box distance minus both
radii; it is exact for boxes and straight runs. A negative gap is a hard clash; a gap
below the 0.05 m clearance is a clearance clash. New runs are checked against columns,
headers, support equipment, existing hookups and each other. The take-off run of a hookup
is exempt only against its own header.

For comparison, the same assignments are also drawn as naive Manhattan L-routes that ignore
obstacles (up to the top routing layer, along x, along y, up to the floor); their length is
the Manhattan lower bound used in the routing summary.

## 7. Outputs

* Hookup list (per tool per utility: POC, header, corridor, size, length, bends, velocity,
  loss split into friction / fittings / static, available pressure, design current for
  power, governing check).
* Material take-off by category / system / material / size; elbows.
* Cost estimate with the illustrative unit rates in `data/unit_rates.json`: material per
  metre (a + b·OD; power: a + rate per ampere of breaker rating), elbows, labour hours ×
  rate, POC tie-in, test, plus process lateral items (header capacity steps, new POCs).
* Schedule: PLS work (header capacity step, new POC) → hookup; tool move-in and set (rigging
  crew) in parallel; test of each hookup after its hookup and the tool set; utilities on /
  handed to the vendor after all of a tool's tests; vendor start-up. Durations from
  illustrative productivity, crew numbers and fixed durations, scheduled by a serial
  schedule-generation scheme in half-day slots (tools in id order); Gantt PNG.
* IFC with the new routes (status `planned`) and planned POCs for viewing.

## 8. Drawing review aid

`review.py` checks a proposal (hookups with POC, size and drawn route, plus the header
capacity steps it relies on) against the database, recomputing everything from the
proposal's own geometry: unknown references, wrong utility at the POC, POC already in use
or used twice, demand above the POC rating, header over capacity (after declared steps),
undersized line (velocity, pressure including the PCW loop, breaker rating), gas model
validity, PCW supply and return on different corridors, PCW return whose loop cannot be
checked because its supply is missing, route not orthogonal, route not connected to POC
and tool, hard and clearance clashes. It uses the planner's own hydraulic and clash
functions.

`evaluate_faults` injects one fault at a time into the planner's own (clean) proposal and
runs two tests:

* a **check-coverage test** with faults constructed to violate each rule (wrong utility,
  undersized line, clash, POC over rating, header over capacity, duplicate POC,
  disconnected route, PCW return on the other corridor). It records whether the targeted
  rule fired and lists every other finding on the faulted hookups. By construction this
  only shows that each check is wired up.
* **faults not targeted by any rule**, written afterwards: the line sized from a flow read
  in the wrong unit (L/min as m³/h, which oversizes it, and m³/h as L/min, which undersizes
  it), a gas line drawn so small that its loss exceeds 10 % of the inlet pressure, PCW
  supply and return swapped at the tool, and a route ending at another tool. A case counts
  as caught if any finding lands on a faulted hookup.

Findings on hookups that were not touched are reported as *explained* when they follow
mechanically from the fault (a clash with the faulted run, a header whose load the fault
changed, the PCW partner of a faulted hookup) and as *unexplained* otherwise. Per-fault
tables are in `results/review_eval.md`.

## 9. Determinism

All floats written to `results/` are rounded to 10 significant digits; lists are sorted;
files use LF endings; IFC GlobalIds and timestamps are fixed; the MILP optimum is made
unique. `results/MANIFEST.sha256` lists a SHA-256 for every result file (for the PNG, a
hash of the decoded pixels, because PNG compression bytes can differ between zlib builds).
The manifest from Windows 11 and from Ubuntu 24.04 (WSL) must be identical.
