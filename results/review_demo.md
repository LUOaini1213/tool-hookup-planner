# Review of a sample proposal with seeded errors

Illustrative synthetic data. Automated checks only; not a substitute for engineering review.

| Check | Severity | Findings |
|---|---|---|
| CLASH_HARD | error | 5 |
| HEADER_OVER_CAPACITY | error | 2 |
| PCW_SPLIT_CORRIDOR | error | 2 |
| POC_IN_USE | error | 2 |
| POC_OVER_RATING | error | 1 |
| ROUTE_DISCONNECTED | error | 5 |
| UNDERSIZED_VELOCITY | error | 1 |
| WRONG_UTILITY | error | 1 |

| Hookup | Check | Detail |
|---|---|---|
| HN-N01-CDA | CLASH_HARD | HN-N01-CDA#0 vs header CDA-C: gap -0.054 m |
| HN-N01-CDA | ROUTE_DISCONNECTED | start not at POC |
| HN-N01-CDA | WRONG_UTILITY | CDA hookup connected to PCWS POC PCWS-A-P12 |
| HN-N01-GEX | UNDERSIZED_VELOCITY | 13.1 m/s > limit 7.62 m/s at D150 |
| HN-N01-N2 | CLASH_HARD | HN-N01-N2#2 vs column C-02-03: gap -0.006 m |
| HN-N01-N2 | CLASH_HARD | HN-N01-N2#3 vs column C-02-03: gap -0.006 m |
| HN-N01-PWR | POC_OVER_RATING | demand 107 > POC rating 69.28 kVA |
| HN-N01-PWR | ROUTE_DISCONNECTED | start not at POC |
| HN-N02-AEX | HEADER_OVER_CAPACITY | header AEX-D: existing 3188 + proposed 2018 > usable 4250 m3/h |
| HN-N02-CDA | CLASH_HARD | HN-N02-CDA#0 vs header CDA-C: gap -0.054 m |
| HN-N02-CDA | POC_IN_USE | POC CDA-A-P06 used by 2 proposed hookups: HN-N02-CDA, HN-N06-CDA |
| HN-N02-CDA | ROUTE_DISCONNECTED | start not at POC |
| HN-N02-N2 | ROUTE_DISCONNECTED | end not at tool connection |
| HN-N02-PCWR | CLASH_HARD | HN-N02-PCWR#0 vs header PCWR-C: gap -0.097 m |
| HN-N02-PCWR | PCW_SPLIT_CORRIDOR | T-N02: PCW supply on corridor C, return on corridor A |
| HN-N02-PCWR | ROUTE_DISCONNECTED | start not at POC |
| HN-N02-PCWS | PCW_SPLIT_CORRIDOR | T-N02: PCW supply on corridor C, return on corridor A |
| HN-N06-CDA | POC_IN_USE | POC CDA-A-P06 used by 2 proposed hookups: HN-N02-CDA, HN-N06-CDA |
| HN-N07-AEX | HEADER_OVER_CAPACITY | header AEX-D: existing 3188 + proposed 2018 > usable 4250 m3/h |

## Seeded errors

- wrong_utility: HN-N01-CDA
- undersized_line: HN-N01-GEX
- clash: HN-N01-N2
- poc_over_rating: HN-N01-PWR
- header_over_capacity: HN-N02-AEX, HN-N07-AEX
- duplicate_poc: HN-N02-CDA, HN-N06-CDA
- disconnected_route: HN-N02-N2
- pcw_split_corridor: HN-N02-PCWR, HN-N02-PCWS
