# Sources

Every engineering rule or physical constant the code relies on is listed here with the
public page it was checked against. All pages were retrieved and read on **2026-10-02**.
The key in the first column is the `SRC_*` tag used in `src/hookup_planner/engineering.py`.

Where a source gives a range, the row states which value the code uses and why; for
roughness the upper end is the *conservative* choice (more friction), for velocity limits
the upper end is the *least restrictive* one. Anything that is *not* in this table is
either plain arithmetic (areas, unit conversions, linear interpolation) or an
**illustrative modelling choice**, listed separately at the end.

## Rules and constants used in calculations

| Key | What the code uses | Source |
|---|---|---|
| SRC_DARCY | Pressure-loss form of Darcy-Weisbach, Δp/L = f_D · ρ/2 · v²/D; f_D = 64/Re for laminar flow | Wikipedia, "Darcy–Weisbach equation", https://en.wikipedia.org/wiki/Darcy%E2%80%93Weisbach_equation |
| SRC_FRICTION_FORMULAE | Swamee–Jain explicit friction factor f = 0.25 / [log10(ε/D/3.7 + 5.74/Re^0.9)]²; stated validity 5000 ≤ Re ≤ 10⁸ and 10⁻⁶ ≤ ε/D ≤ 0.05; laminar below Re 2300, transition 2300–4000. The code uses 64/Re below 2300 and Swamee–Jain above, and labels 2300 ≤ Re < 5000 as `transition` (outside the stated Swamee–Jain range) in the hookup list. | Wikipedia, "Darcy friction factor formulae", https://en.wikipedia.org/wiki/Darcy_friction_factor_formulae |
| SRC_WATER_VELOCITY | Maximum water velocity: "Cooling water 1.5 - 2.5 m/s" (PCW supply/return use the upper end, 2.5 m/s) and "Process water 1.5 - 3 m/s" (UPW uses the upper end, 3.0 m/s; treating UPW as process water is this project's assumption) | Engineering ToolBox, "Water Systems - Maximum Flow Velocities", https://www.engineeringtoolbox.com/flow-velocity-water-pipes-d_385.html |
| SRC_CDA_VELOCITY | Compressed-air pipe velocity: the article quotes British Compressed Air Society guidance of 6-7 m/s or less for main headers and "never to exceed 9m/s". Hookups use 9 m/s as the hard limit; the same limit is applied to nitrogen (assumption). | Atlas Copco blog, "How to size compressed air piping?", https://www.atlascopco.com/en-us/compressors/air-compressor-blog/sizing-compressed-air-pipe |
| SRC_DUCT_VELOCITY | Range of minimum duct design velocities for "Vapors, gases, smoke — All vapors, gases, and smoke": 1000–2000 ft/min (5.08–10.16 m/s). The code uses **1500 ft/min (7.62 m/s) as a design velocity**, the middle of that range, as the sizing ceiling for general/acid/solvent exhaust branch ducts (smallest duct at or below 7.62 m/s), and reports ducts that end up below 1000 ft/min. (1) 2025 California Mechanical Code, Table 505.9 "Range of minimum duct design velocities" (referenced from Section 505.9 for product-conveying ducts), as reproduced on a code-viewer site; (2) a CIH study guide that attributes the same 1,000–2,000 fpm (5.0–10.0 m/s) for gases and vapours to the ACGIH *Industrial Ventilation* manual (the manual itself is not public). | (1) https://gocodebook.com/library/us/ca/ca-mechanical-code/chapter-5-exhaust-systems/506.1-materials.-materials-used-in-product-conveying-duct ; (2) OpenExamPrep, "Particulate Transport Aerodynamics and Duct Sizing", https://open-exam-prep.com/study-guides/cih/ventilation-lev-design/duct-design-transport-velocity |
| SRC_FOOT | 1 ft = 0.3048 m exactly (used for the ft/min to m/s conversion) | Wikipedia, "Foot (unit)", https://en.wikipedia.org/wiki/Foot_(unit) |
| SRC_INCH | 1 in = 25.4 mm exactly (tube outside diameters and walls) | Wikipedia, "Inch", https://en.wikipedia.org/wiki/Inch |
| SRC_ROUGHNESS | Absolute roughness, per row: stainless steel "bead blasted" 0.001–0.006 mm and "turned" 0.0004–0.006 mm → code uses 0.006 mm (upper end, conservative) for PCW pipe and solvent-exhaust duct; stainless steel "electron-polished" (electropolished) 0.0001–0.0008 mm → 0.0008 mm (upper end, conservative) for the CDA/N2 tubing; "PVC, PE and other smooth Plastic Pipes" 0.0015–0.007 mm → 0.007 mm (upper end, conservative) for UPW pipe and acid-exhaust duct; galvanized steel 0.15 mm (single value) for general-exhaust duct | Engineering ToolBox, "Surface Roughness Coefficients", https://www.engineeringtoolbox.com/surface-roughness-ventilation-ducts-d_209.html |
| SRC_MINOR_LOSS | Minor loss Δp = ξ ρ v²/2 with ξ = 0.3 for "Elbow, Flanged Regular 90°" (one per route bend), ξ = 1.0 for "Tee, Flanged, Dividing Branched Flow" (one per fluid hookup, at the take-off from the header) and ξ = 0.05 for "Ball Valve, Fully Open" (one per pipe/tube hookup, the POC isolation valve), all on the hookup velocity. The table lists flanged and threaded fittings only; using the flanged values for welded or fused fittings, using the dividing-flow tee value also where a return joins its header, and applying the pipe values to ducts are this project's assumptions (see README limitations). | Engineering ToolBox, minor loss coefficients, https://www.engineeringtoolbox.com/minor-loss-coefficients-pipes-d_626.html |
| SRC_NPS | Outside diameters and Schedule 10S wall thickness for NPS 1/2 to 6 (pipe inner diameter = OD − 2·wall); used for PCW and UPW | Wikipedia, "Nominal Pipe Size", https://en.wikipedia.org/wiki/Nominal_Pipe_Size |
| SRC_TUBE | OD-sized stainless tubing for CDA/N2 hookups: 1/2, 3/4, 1, 1 1/2 and 2 in outside diameter, 0.065 in wall (bore = OD − 2·wall). The table is for ASTM A270 sanitary tubing; fab gas tubing is usually specified to other standards whose walls may differ (README limitations). | Engineering ToolBox, "ASTM A270 Sanitary Stainless Steel Tubing - Dimensions", https://www.engineeringtoolbox.com/ASTM-A270-sanitary-stainless-steel-tubing-d_2160.html |
| SRC_WATER_DENSITY | Water density 998.21 kg/m³ at 20 °C | Engineering ToolBox, water density table, https://www.engineeringtoolbox.com/water-density-specific-weight-d_595.html |
| SRC_WATER_VISCOSITY | Water dynamic viscosity 1.0016 mPa·s at 20 °C | Engineering ToolBox, water viscosity table, https://www.engineeringtoolbox.com/water-dynamic-kinematic-viscosity-d_596.html |
| SRC_AIR_VISCOSITY | Air dynamic viscosity 18.13 µPa·s at 20 °C, 1 atm (used for CDA and exhaust air; pressure dependence ignored) | Engineering ToolBox, air viscosity table, https://www.engineeringtoolbox.com/air-absolute-kinematic-viscosity-d_601.html |
| SRC_N2_VISCOSITY | Nitrogen dynamic viscosity at 1 bar: 16.96 µPa·s at 280 K and 17.89 µPa·s at 300 K (the page has no 20 °C row); the code interpolates linearly to 293.15 K, giving 17.57 µPa·s. Pressure dependence ignored. | Engineering ToolBox, nitrogen viscosity table, https://www.engineeringtoolbox.com/nitrogen-N2-dynamic-kinematic-viscosity-temperature-pressure-d_2067.html |
| SRC_AIR_MOLAR_MASS | Molar mass of dry air 28.9647 g/mol | Engineering ToolBox, https://www.engineeringtoolbox.com/molecular-mass-air-d_679.html |
| SRC_N_ATOMIC_WEIGHT | Nitrogen standard atomic weight (abridged) 14.007, so N₂ = 28.014 g/mol | Wikipedia, "Nitrogen", https://en.wikipedia.org/wiki/Nitrogen |
| SRC_GAS_CONSTANT | Molar gas constant R = 8.31446261815324 J/(mol·K); gas density ρ = p·M/(R·T) (ideal gas), also used for the ambient air density (1.2041 kg/m³ at 101.325 kPa and 20 °C) | Wikipedia, "Gas constant", https://en.wikipedia.org/wiki/Gas_constant |
| SRC_STD_M3 | Standard cubic metre reference conditions 15 °C and 101.325 kPa (the page states them for natural gas; this project adopts them for its Sm³/h gas flows) | Wikipedia, "Standard cubic foot" (section on the standard cubic metre), https://en.wikipedia.org/wiki/Standard_cubic_foot |
| SRC_GRAVITY | Standard gravity 9.80665 m/s² | Wikipedia, "Standard gravity", https://en.wikipedia.org/wiki/Standard_gravity |
| SRC_HYDROSTATIC | Static pressure difference Δp = ρ g Δz for constant density | Wikipedia, "Hydrostatic pressure", https://en.wikipedia.org/wiki/Hydrostatic_pressure |
| SRC_GAUGE_PRESSURE | "Gauge pressure is zero-referenced against ambient air pressure, so it is equal to absolute pressure minus atmospheric pressure"; atmospheric pressure "is variable with altitude". All pressures in the model are gauge, so over a rise Δz the reference itself falls by ρ_air g Δz. | Wikipedia, "Pressure measurement", https://en.wikipedia.org/wiki/Pressure_measurement |
| SRC_STACK_EFFECT | Natural-draft (stack) pressure between two air columns of different density: dp = g (ρ_o − ρ_r) h. Together with the two rows above, the change in *gauge* pressure along a hookup that rises Δz in the flow direction is (ρ_fluid − ρ_air) g Δz. For room-temperature exhaust ρ_fluid ≈ ρ_air and the term is ≈ 0; for CDA/N2 at 700 kPa g it is about 13 % smaller than ρ g Δz; for water about 0.1 %. The temperature form of the same effect is on Wikipedia, "Stack effect" (https://en.wikipedia.org/wiki/Stack_effect). | Engineering ToolBox, "Natural Draft - Air Flow Volume and Velocity", https://www.engineeringtoolbox.com/natural-draught-ventilation-d_122.html |
| SRC_COMPRESSIBLE_DARCY | Darcy-Weisbach may be used for gas if the pressure drop is less than ten percent of the absolute inlet pressure (with inlet density). The code flags any gas or exhaust hookup that breaks this as `MODEL_INVALID` and will not size to it. | Pipe Flow Wizard help, "Darcy-Weisbach Formula", https://www.pipeflow.com/public/PipeFlowWizardSoftwareHelp/html/Darcy-WeisbachFormula.html |
| SRC_THREE_PHASE | Line-to-line voltage is √3 times line-to-neutral, with "230/400 V" given as the example for countries with 230 V line-to-neutral (the code uses 400 V line-to-line; the choice of voltage is illustrative); apparent power S = √3 × V_line × I_line, and in a star connection line and phase current are the same. Design current I = S / (√3 · 400 V). | Wikipedia, "Three-phase electric power", https://en.wikipedia.org/wiki/Three-phase_electric_power ; Omni Calculator, "Three-Phase Calculator", https://www.omnicalculator.com/physics/three-phase |
| SRC_NEC_CONTINUOUS | NEC 210.20(A) as quoted in the article: "the rating of the overcurrent device shall not be less than the noncontinuous load plus 125 percent of the continuous load", a continuous load being one whose maximum current "is expected to continue for 3 hours or more" (NEC Article 100). Tool loads are treated as continuous, so a feeder breaker must be rated ≥ 1.25 × design current. This is a US rule; it is used here as a stated, conservative convention (the IEC practice of rating the device for the design current was not retrieved from a public source). | T. A. Domitrovich, "100% vs 80%: choosing the right OCPD solution", IAEI Magazine, May–June 2016, https://iaeimagazine.org/2016/may2016/100-vs-80-choosing-the-right-ocpd-solution/ |
| SRC_COINCIDENCE | Definition: diversity factor = sum of individual peak loads / peak of the combined load; the coincidence factor is its reciprocal. The page gives no numeric value for industrial process loads, and none was found elsewhere, so **every coincidence factor is 1.0** (no diversity credit; loads are summed at peak). The factor is a column in the database so a cited value can be entered later. | Wikipedia, "Diversity factor", https://en.wikipedia.org/wiki/Diversity_factor |

## Context only (not implemented)

| Topic | What the source says (paraphrased) | Source |
|---|---|---|
| UPW dead legs | The guide reports that proposed (never finalised) LVP regulations defined a dead leg as an unused portion longer than six diameters of the unused pipe, measured from the axis of the pipe in use, and notes this was developed for hot (75–80 °C) circulating systems. The model has no valve positions at a branch, so no dead-leg check is made (README limitations). | U.S. FDA, "High Purity Water System (7/93)", inspection guide, https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/inspection-guides/high-purity-water-system-793 |

## Algorithms and libraries

| Key | Use | Source (retrieved 2026-10-02) |
|---|---|---|
| SRC_ASTAR | A* returns a least-cost path when the heuristic is admissible; Hart, Nilsson & Raphael (1968), "A Formal Basis for the Heuristic Determination of Minimum Cost Paths", IEEE Trans. SSC 4(2). The Manhattan step count × step cost never exceeds the true cost (bend penalties are non-negative), so it is admissible; `tests/test_geometry_lattice.py` checks A* against plain Dijkstra on random grids. | Wikipedia, "A* search algorithm", https://en.wikipedia.org/wiki/A*_search_algorithm |
| SRC_MILP | `scipy.optimize.milp`, a wrapper of the HiGHS solver | SciPy docs, https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html |
| SRC_LSA | `scipy.optimize.linear_sum_assignment` (rectangular assignment, modified Jonker-Volgenant) as an independent check of the relaxed assignment (no capacity, no pairing) | SciPy docs, https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html |
| IFC4 | Entity and enumeration names (IfcPipeSegment, IfcDuctSegment, IfcCableSegment BUSBARSEGMENT/CABLESEGMENT, IfcValve, IfcDamper, IfcProtectiveDevice, IfcDistributionSystem, IfcDistributionPort, IfcRelNests, IfcRelConnectsPorts, IfcDerivedUnit, IfcConversionBasedUnit, ...) were checked against the IFC4 schema bundled with IfcOpenShell 0.8.5, and the written files against its validator with EXPRESS rules on. The header view name `ReferenceView_V1.2` is the IFC4 default in IfcOpenShell's file template (`ifcopenshell/template.py`) and its bundled `ReferenceView_V1-2.mvdxml`. The buildingSMART HTML pages returned HTTP 403 to the fetcher, so no URL is given. | IfcOpenShell 0.8.5 schema, validator and template |

## SEMI standards (context only)

SEMI standards are paywalled. Only the public store descriptions below were read; no
clause content is used or reproduced, and no rule in the code comes from them.

| Standard | Public description says (paraphrased) | Page |
|---|---|---|
| SEMI E6 - Guide for Semiconductor Equipment Installation Documentation (E6-0914, shown as inactive) | Standardised data sheets so suppliers and fabs can communicate the facility information needed to prepare the site and install equipment, from receiving through hookup | https://store-us.semi.org/products/e00600-semi-e6-guide-for-semiconductor-equipment-installation-documentation |
| SEMI E76 - Guide for 300 mm Process Equipment Points of Connection to Facility Services (E76-0299, reapproved 0913, shown as inactive) | Recommendations on equipment point-of-connection location and consistency, pre-facilitation of utility POCs, and documentation of POC locations | https://store-us.semi.org/products/e07600-semi-e76-guide-for-300-mm-process-equipment-points-of-connection-to-facility-services |
| SEMI F122 - Guide for Facilities Data Package for Manufacturing Equipment Installation and Building Information Modeling (F122-0225) | Suggested formats for the facilities data package and BIM data used to plan facility preparation and equipment hookup | https://store-us.semi.org/products/f12200-semi-f122-guide-for-facilities-data-package-for-manufacturing-equipment-installation-and-building-information-modeling |

The tool demand records in this repository (flow, pressure, connection point per utility)
are the kind of information such data packages carry; their format here is this project's
own and is not taken from any SEMI document.

## Illustrative modelling choices (not engineering rules)

These values are invented for the synthetic demonstration and are not sourced:

- Everything in `data/scenario.json` (layout, header sizes, pressures, capacities, tool
  demands, pressure requirements and PCW tool pressure drops, POC sizes) and
  `data/unit_rates.json` (all costs, productivity, crew numbers, durations including
  move-in/set and vendor start-up).
- Operating temperature 20 °C for every fluid and for the ambient air.
- Line-to-line voltage 400 V (one of the cited nominal voltages).
- Clash clearance 0.05 m between outer surfaces.
- Routing lattice 0.6 m; A* bend penalty equal to one lattice step.
- Round duct catalogue D100-D600 in 50 mm steps; breaker ratings 32-400 A.
- PCW supply and return of a tool on the same corridor (a planning rule of this project).
- Header capacity "reserve" (0 % in the headline run; 2, 5, 10 and 20 % in the sensitivity table).
