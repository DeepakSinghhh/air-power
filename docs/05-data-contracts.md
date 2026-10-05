# 05 · Data contracts (generated from `backend/tatpar/ingest/contracts.py`)

How a unit feeds its own data into TATPAR. Each source is a CSV export; `POST /api/ingest/{source}` validates it row by row against the contract below and the fleet register, then applies the accepted rows. `POST /api/ingest/{source}/validate` checks a file without storing anything. Templates and samples: `GET /api/ingest/template/{source}` (add `?sample=true`), or `data/samples/`.

Every import is recorded with its file hash, row counts and the signed-in user, and written to the hash-chained decision ledger. `python -m tatpar.ingest reset` removes all imported data.

## `hums` — HUMS / ACMS engine download

*Produced by:* Ground station export of the engine health-monitoring recorder, one row per engine cycle. *Entity:* EngineHealthSnapshot (S5000F: Health monitoring data; OSA-CBM: DA → DM).

*What an import changes:* Appended to the engine's health history; the RUL model re-predicts with a calibrated 90 % interval and module attribution. The new interval replaces the stored one everywhere: alerts, risk, Monte-Carlo forecasts, engine protection in the flight plan and the planner.

*Record key:* tail + engine + cycle (a later duplicate replaces an earlier one).

| Field | Type | Unit | Required | Allowed | Meaning |
|---|---|---|---|---|---|
| `tail` | str |  | yes | a tail in the fleet register | Aircraft tail number, e.g. HF-107 |
| `engine` | int |  | yes | 1 – 2 | Engine position on the aircraft (1 = left / single) |
| `cycle` | int | cycles | yes | 1 – 2000 | Engine cycle number since the module was fitted |
| `date` | date |  | no |  | Flight date of the cycle |
| `setting1` | float | kft | yes | -1 – 45 | Altitude |
| `setting2` | float | Mach | yes | -0.05 – 0.9 | Mach number |
| `setting3` | float | deg | yes | 50 – 105 | Throttle resolver angle |
| `T2` | float | °R | no | 433.945 – 529.755 | Total temperature at fan inlet (optional: not used by the RUL model) |
| `T24` | float | °R | yes | 519.06 – 661.54 | Total temperature at LPC outlet |
| `T30` | float | °R | yes | 1186.57 – 1673.03 | Total temperature at HPC outlet |
| `T50` | float | °R | yes | 961.145 – 1504.15 | Total temperature at LPT outlet |
| `P2` | float | psia | no | 2.295 – 16.205 | Pressure at fan inlet (optional: not used by the RUL model) |
| `P15` | float | psia | no | 3.315 – 23.985 | Total pressure in bypass duct (optional: not used by the RUL model) |
| `P30` | float | psia | yes | 71.01 – 635.99 | Total pressure at HPC outlet |
| `Nf` | float | rpm | yes | 1843.62 – 2459.68 | Physical fan speed |
| `Nc` | float | rpm | yes | 7795.48 – 9433.61 | Physical core speed |
| `epr` | float | — | no | 0.872 – 1.379 | Engine pressure ratio (P50/P2) (optional: not used by the RUL model) |
| `Ps30` | float | psia | yes | 34.125 – 50.375 | Static pressure at HPC outlet |
| `phi` | float | pps/psi | yes | 66.92 – 598.88 | Ratio of fuel flow to Ps30 |
| `NRf` | float | rpm | yes | 1973.16 – 2444.93 | Corrected fan speed |
| `NRc` | float | rpm | yes | 7778.61 – 8360.89 | Corrected core speed |
| `BPR` | float | — | yes | 7.724 – 11.507 | Bypass ratio |
| `farB` | float | — | no | 0.018 – 0.032 | Burner fuel-air ratio (optional: not used by the RUL model) |
| `htBleed` | float | — | yes | 287.3 – 414.7 | Bleed enthalpy |
| `Nf_dmd` | float | rpm | no | 1844.05 – 2458.95 | Demanded fan speed (optional: not used by the RUL model) |
| `PCNfR_dmd` | float | % | no | 82.635 – 102.265 | Demanded corrected fan speed (optional: not used by the RUL model) |
| `W31` | float | lbm/s | yes | 5.745 – 44.355 | HPT coolant bleed |
| `W32` | float | lbm/s | yes | 3.3 – 26.7 | LPT coolant bleed |

> Layout follows NASA C-MAPSS (3 operating settings, 21 sensors). A real fleet's HUMS channels map onto it; the model must be retrained on that fleet's own history before its numbers are trusted.
> At least 5 cycles per engine; 30 or more gives the full rolling-window features.

## `snags` — Technical log (Form-700 / e-MMS)

*Produced by:* e-MMS or Form-700 export of defect entries. *Entity:* Snag (S5000F: Failure / malfunction report; OSA-CBM: SD).

*What an import changes:* Filed in the aircraft's technical log, auto-coded to an ATA chapter with similar past cases, and checked for repeat defects on the same tail and system.

| Field | Type | Unit | Required | Allowed | Meaning |
|---|---|---|---|---|---|
| `date` | date |  | yes |  | Date the defect was raised |
| `tail` | str |  | yes | a tail in the fleet register |  |
| `text` | str |  | yes |  | Defect text as written; Hinglish and abbreviations are fine |
| `lru` | str |  | no | an LRU code | LRU code if known (see /api/meta), e.g. HYD_PUMP |
| `reported_by` | str |  | no |  | Who raised it |

## `stock` — Stock levels (IMMOLS)

*Produced by:* IMMOLS stock-on-hand report per stock point. *Entity:* StockLevel (S5000F: Material supply (S2000M); OSA-CBM: —).

*What an import changes:* Sets the serviceable stock at that stock point; forecasts, sparing, transfers and the planner use it.

*Record key:* stock_point + lru (a later duplicate replaces an earlier one).

| Field | Type | Unit | Required | Allowed | Meaning |
|---|---|---|---|---|---|
| `stock_point` | enum |  | yes | jodhpur, pune, tezpur, thanjavur, ED | Base store or ED (equipment depot) |
| `lru` | str |  | yes | an LRU code | LRU code |
| `qty` | int | units | yes | 0 – 500 | Serviceable units on hand |
| `as_of` | date |  | no |  |  |

## `repairs` — Repair-order status (BRD / HAL)

*Produced by:* Repair agency status report for units under repair. *Entity:* RepairOrder (S5000F: Repair / overhaul event; OSA-CBM: —).

*What an import changes:* Updates the unit's return date (or condemns it) in the repair pipeline; spares availability, forecasts and the depot-expedite advice follow.

*Record key:* serial (a later duplicate replaces an earlier one).

| Field | Type | Unit | Required | Allowed | Meaning |
|---|---|---|---|---|---|
| `serial` | int |  | yes | a known serial | Serial number of the unit under repair (S/N) |
| `lru` | str |  | yes | an LRU code | LRU code; must match the serial |
| `agency` | enum |  | yes | BRD, HAL |  |
| `status` | enum |  | yes | IN_WORK, AWAITING_PARTS, BER | BER = beyond economic repair (condemned) |
| `expected_return` | date |  | yes |  | Agency's promised return date |
| `finding` | enum |  | no | CONFIRMED, NFF | Shop finding, if known |

## `sorties` — Flying records

*Produced by:* Squadron flying log. *Entity:* Sortie (S5000F: Operation / usage; OSA-CBM: DA).

*What an import changes:* Validated against the contract; usage feeds the survival models at the next retrain (make train).

| Field | Type | Unit | Required | Allowed | Meaning |
|---|---|---|---|---|---|
| `date` | date |  | yes |  |  |
| `tail` | str |  | yes | a tail in the fleet register |  |
| `hours` | float | FH | yes | 0.1 – 8 |  |
| `mission` | enum |  | no | training, air_combat, strike, recce_nav |  |
