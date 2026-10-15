# Hookup list

ILLUSTRATIVE synthetic data. Pressure loss: Darcy-Weisbach with Swamee-Jain friction factor, fitting losses (elbows, branch tee, POC valve) and the static term (rho_fluid - rho_air) g dz; see docs/sources.md. PCWR: available = supply header - supply hookup loss - tool pressure drop - return header. Power: design current at 400 V three-phase; breaker >= 1.25 x design current.

| Hookup | Tool | Utility | POC | Size | Length m | Bends | Velocity m/s | Static kPa | dP kPa | Available kPa | Governed by | OK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HN-N01-CDA | T-N01 | CDA | CDA-C-P04 | OD 3/4 in | 10.2 | 3 | 5.14 | 0.245 | 2.26 | 85 | velocity | yes |
| HN-N01-GEX | T-N01 | GEX | GEX-D-P04 | D200 | 4.8 | 3 | 7.35 | 0.00042 | 0.078 | 0.65 | velocity | yes |
| HN-N01-N2 | T-N01 | N2 | N2-C-P04 | OD 1/2 in | 7.8 | 2 | 7.73 | 0.236 | 5.8 | 10 | velocity | yes |
| HN-N01-PWR | T-N01 | PWR | PWR-D-P03 | 200 A | 7.8 | 4 |  |  | 154 A design |  | rating | yes |
| HN-N02-AEX | T-N02 | AEX | AEX-D-P10 | D200 | 6.0 | 2 | 5.90 | 0.000587 | 0.0455 | 0.85 | velocity | yes |
| HN-N02-CDA | T-N02 | CDA | CDA-C-P11 | OD 3/4 in | 13.8 | 4 | 6.60 | 0.245 | 4.46 | 50 | velocity | yes |
| HN-N02-N2 | T-N02 | N2 | N2-C-P11 | OD 3/4 in | 15.0 | 5 | 3.30 | 0.236 | 1.51 | 45 | velocity | yes |
| HN-N02-PCWR | T-N02 | PCWR | PCWR-C-P10 | NPS 3/4 | 9.6 | 2 | 2.02 | -46.9 | -24.2 | 135 | velocity | yes |
| HN-N02-PCWS | T-N02 | PCWS | PCWS-C-P10 | NPS 3/4 | 12.0 | 3 | 2.02 | 46.9 | 75.1 | 140 | velocity | yes |
| HN-N02-PWR | T-N02 | PWR | PWR-D-P10 | 63 A | 7.8 | 4 |  |  | 33 A design |  | rating | yes |
| HN-N02-SEX | T-N02 | SEX | SEX-D-P10 | D200 | 6.0 | 3 | 6.12 | 0.000587 | 0.0555 | 1 | velocity | yes |
| HN-N02-UPW | T-N02 | UPW | UPW-C-P09 | NPS 3/4 | 12.6 | 5 | 2.23 | 35.2 | 72.2 | 100 | velocity | yes |
| HN-N03-CDA | T-N03 | CDA | CDA-A-P09 | OD 3/4 in | 4.8 | 3 | 6.42 | 0.245 | 1.87 | 75 | velocity | yes |
| HN-N03-GEX | T-N03 | GEX | GEX-B-P09 | D200 | 11.4 | 3 | 6.89 | 0.00042 | 0.0889 | 0.6 | velocity | yes |
| HN-N03-N2 | T-N03 | N2 | N2-A-P10 | OD 3/4 in | 8.4 | 3 | 5.32 | 0.236 | 1.99 | 80 | velocity | yes |
| HN-N03-PWR | T-N03 | PWR | PWR-B-N054 (new) | 250 A | 9.0 | 3 |  |  | 176 A design |  | rating | yes |
| HN-N04-CDA | T-N04 | CDA | CDA-C-P09 | OD 1/2 in | 3.6 | 2 | 4.64 | 0.245 | 1.4 | 30 | velocity | yes |
| HN-N04-GEX | T-N04 | GEX | GEX-D-P09 | D200 | 10.2 | 4 | 5.50 | 0.00042 | 0.0604 | 0.8 | velocity | yes |
| HN-N04-N2 | T-N04 | N2 | N2-C-P08 | OD 1/2 in | 8.4 | 4 | 6.18 | 0.236 | 4.34 | 35 | velocity | yes |
| HN-N04-PCWR | T-N04 | PCWR | PCWR-A-P10 | NPS 1/2 | 19.8 | 5 | 2.39 | -46.9 | 36 | 59.7 | velocity | yes |
| HN-N04-PCWS | T-N04 | PCWS | PCWS-A-P09 | NPS 1/2 | 18.6 | 5 | 2.39 | 46.9 | 125 | 140 | velocity | yes |
| HN-N04-PWR | T-N04 | PWR | PWR-D-P06 | 200 A | 18.0 | 4 |  |  | 159 A design |  | rating | yes |
| HN-N04-SEX | T-N04 | SEX | SEX-B-P09 | D200 | 11.4 | 3 | 5.84 | 0.000587 | 0.0613 | 0.85 | velocity | yes |
| HN-N05-AEX | T-N05 | AEX | AEX-B-P01 | D200 | 6.6 | 3 | 4.69 | 0.000587 | 0.034 | 0.6 | velocity | yes |
| HN-N05-CDA | T-N05 | CDA | CDA-C-P02 | OD 1/2 in | 14.4 | 4 | 3.09 | 0.245 | 2.29 | 55 | velocity | yes |
| HN-N05-GEX | T-N05 | GEX | GEX-B-P01 | D250 | 4.2 | 3 | 6.51 | 0.00042 | 0.0571 | 0.75 | velocity | yes |
| HN-N05-N2 | T-N05 | N2 | N2-A-P01 | OD 3/4 in | 9.6 | 3 | 7.52 | 0.236 | 3.92 | 25 | velocity | yes |
| HN-N05-PCWR | T-N05 | PCWR | PCWR-C-P04 | NPS 3/4 | 24.6 | 5 | 2.06 | -46.9 | 10 | 128 | velocity | yes |
| HN-N05-PCWS | T-N05 | PCWS | PCWS-C-P02 | NPS 1 | 17.4 | 3 | 1.34 | 46.9 | 61.5 | 85 | pressure | yes |
| HN-N05-PWR | T-N05 | PWR | PWR-B-P01 | 200 A | 8.4 | 4 |  |  | 134 A design |  | rating | yes |
| HN-N06-AEX | T-N06 | AEX | AEX-B-P06 | D200 | 6.0 | 2 | 7.28 | 0.000587 | 0.0682 | 0.6 | velocity | yes |
| HN-N06-CDA | T-N06 | CDA | CDA-A-P06 | OD 3/4 in | 11.4 | 4 | 6.05 | 0.245 | 3.29 | 90 | velocity | yes |
| HN-N06-N2 | T-N06 | N2 | N2-A-P06 | OD 3/4 in | 11.4 | 4 | 5.32 | 0.236 | 2.56 | 40 | velocity | yes |
| HN-N06-PCWR | T-N06 | PCWR | PCWR-A-P06 | NPS 3/4 | 9.6 | 2 | 2.48 | -46.9 | -13.7 | 188 | velocity | yes |
| HN-N06-PCWS | T-N06 | PCWS | PCWS-A-P06 | NPS 1 | 12.0 | 3 | 1.61 | 46.9 | 61.8 | 80 | pressure | yes |
| HN-N06-PWR | T-N06 | PWR | PWR-B-P05 | 160 A | 10.2 | 6 |  |  | 115 A design |  | rating | yes |
| HN-N06-SEX | T-N06 | SEX | SEX-B-P06 | D200 | 6.0 | 3 | 6.56 | 0.000587 | 0.0635 | 0.9 | velocity | yes |
| HN-N06-UPW | T-N06 | UPW | UPW-A-P06 | NPS 3/4 | 11.4 | 4 | 1.56 | 35.2 | 52.4 | 85 | pressure | yes |
| HN-N07-AEX | T-N07 | AEX | AEX-D-P09 | D300 | 6.6 | 3 | 5.31 | 0.000587 | 0.039 | 0.85 | velocity | yes |
| HN-N07-CDA | T-N07 | CDA | CDA-C-P06 | OD 1/2 in | 20.4 | 7 | 3.61 | 0.245 | 4.04 | 20 | velocity | yes |
| HN-N07-GEX | T-N07 | GEX | GEX-D-P08 | D150 | 6.6 | 3 | 5.74 | 0.00042 | 0.0581 | 0.8 | velocity | yes |
| HN-N07-N2 | T-N07 | N2 | N2-C-P06 | OD 1 in | 21.6 | 7 | 6.99 | 0.236 | 5.09 | 90 | velocity | yes |
| HN-N07-PCWR | T-N07 | PCWR | PCWR-A-P09 | NPS 1 | 25.8 | 5 | 2.11 | -46.9 | 1.66 | 113 | velocity | yes |
| HN-N07-PCWS | T-N07 | PCWS | PCWS-A-P10 | NPS 1 1/4 | 29.4 | 7 | 1.22 | 46.9 | 62.3 | 70 | pressure | yes |
| HN-N07-PWR | T-N07 | PWR | PWR-D-N048 (new) | 200 A | 7.8 | 3 |  |  | 136 A design |  | rating | yes |
| HN-N08-CDA | T-N08 | CDA | CDA-A-P01 | OD 3/4 in | 5.4 | 2 | 3.30 | 0.245 | 0.759 | 95 | velocity | yes |
| HN-N08-GEX | T-N08 | GEX | GEX-B-P04 | D200 | 18.0 | 6 | 7.36 | 0.00042 | 0.153 | 0.95 | velocity | yes |
| HN-N08-N2 | T-N08 | N2 | N2-A-P05 | OD 1 in | 15.0 | 4 | 6.43 | 0.236 | 3.14 | 65 | velocity | yes |
| HN-N08-PCWR | T-N08 | PCWR | PCWR-C-P03 | NPS 3/4 | 25.2 | 6 | 1.98 | -46.9 | 7.61 | 89.1 | velocity | yes |
| HN-N08-PCWS | T-N08 | PCWS | PCWS-C-P03 | NPS 3/4 | 25.2 | 5 | 1.98 | 46.9 | 101 | 140 | velocity | yes |
| HN-N08-PWR | T-N08 | PWR | PWR-B-N006 (new) | 250 A | 6.0 | 3 |  |  | 198 A design |  | rating | yes |
| HN-N08-SEX | T-N08 | SEX | SEX-B-P01 | D150 | 15.6 | 6 | 3.41 | 0.000587 | 0.0364 | 0.7 | velocity | yes |
