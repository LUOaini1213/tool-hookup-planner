# Review aid: fault-injection results

ILLUSTRATIVE synthetic data. One fault at a time is injected into the planner's own (clean) proposal.

## Check-coverage test (faults constructed to violate each rule)

Each fault below was written to break one specific rule, so detection is expected by construction; the table only shows that each check is wired up. Findings elsewhere are *explained* when they follow mechanically from the fault (clash with the faulted run, load of a header the fault changed, PCW partner of a faulted hookup).

| Fault | Cases | Expected rule fired | All findings on the faulted hookups (count) | Explained elsewhere | Unexplained elsewhere |
|---|---|---|---|---|---|
| wrong_utility | 8 | 8 | CLASH_HARD 8, POC_OVER_RATING 1, ROUTE_DISCONNECTED 8, WRONG_UTILITY 8 | 0 | 0 |
| undersized_line | 8 | 8 | UNDERSIZED_PRESSURE 3, UNDERSIZED_RATING 1, UNDERSIZED_VELOCITY 7 | 1 | 0 |
| clash | 8 | 8 | CLASH_HARD 8, UNDERSIZED_PRESSURE 1 | 21 | 0 |
| poc_over_rating | 8 | 8 | CLASH_HARD 6, HEADER_OVER_CAPACITY 3, POC_OVER_RATING 8, ROUTE_DISCONNECTED 8 | 12 | 0 |
| header_over_capacity | 2 | 2 | HEADER_OVER_CAPACITY 2 | 0 | 0 |
| duplicate_poc | 8 | 8 | CLASH_HARD 4, HEADER_OVER_CAPACITY 2, POC_IN_USE 8, POC_OVER_RATING 1, ROUTE_DISCONNECTED 8 | 6 | 0 |
| disconnected_route | 8 | 8 | ROUTE_DISCONNECTED 8 | 0 | 0 |
| pcw_split_corridor | 6 | 6 | CLASH_HARD 6, PCW_SPLIT_CORRIDOR 6, ROUTE_DISCONNECTED 6 | 0 | 0 |

## Faults not targeted by any rule

Written after the checks, with no rule aimed at them. A case is caught if any finding lands on a faulted hookup.

| Fault | Cases | Caught | Findings on the faulted hookups (count) | Explained elsewhere | Unexplained elsewhere |
|---|---|---|---|---|---|
| unit_lpm_read_as_m3h | 8 | 0 | - | 0 | 0 |
| unit_m3h_read_as_lpm | 8 | 8 | MODEL_INVALID 1, UNDERSIZED_PRESSURE 5, UNDERSIZED_VELOCITY 8 | 0 | 0 |
| gas_dp_over_10pct | 2 | 2 | MODEL_INVALID 2, UNDERSIZED_PRESSURE 2, UNDERSIZED_VELOCITY 2 | 0 | 0 |
| supply_return_swapped | 6 | 6 | CLASH_HARD 6, ROUTE_DISCONNECTED 6 | 0 | 0 |
| route_to_wrong_tool | 8 | 8 | CLASH_HARD 8, ROUTE_DISCONNECTED 8, UNDERSIZED_PRESSURE 2 | 26 | 0 |
