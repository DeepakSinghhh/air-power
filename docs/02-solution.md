# 02 · Solution — TATPAR (तत्पर, "ever-ready")

> **Others predict failures. TATPAR assures readiness.**

TATPAR is a readiness-assurance platform for air fleets. It joins up health monitoring, technical records, spares and repair-agency data, then plans flying, maintenance and spares positioning to **deliver a required number of mission-capable aircraft on the day of need, with stated confidence**.

## 1. The three commander questions

| Question | TATPAR capability | How it works |
|---|---|---|
| **"How many aircraft will I have on day D — and how sure are you?"** | **Readiness Forecast** | A *Fleet Twin* (simulation of aircraft + spares + BRD/HAL pipeline + bays + manpower) is run hundreds of times with failures sampled from calibrated prognostics → P10–P90 fan chart of MC aircraft per day and P(meet requirement) |
| **"What must I do today to have N ready on day D?"** | **Readiness-Backward Planner** | Commander states a requirement (e.g. *18 MC at Jodhpur, D+10…D+13, 3 sorties/day*). TATPAR jointly optimises flying hours per tail, check timing, spares transfers, depot repair priority and cannibalisation; reports each action's readiness gain; a human approves and the decision is logged |
| **"Where is readiness being lost — and why?"** | **Readiness-Loss Waterfall** | Possessed aircraft-days decomposed into awaiting-spares, scheduled, unscheduled, depot and manpower losses, with counterfactual "recoverable days" per lever |

## 2. Core engines

### 2.1 Calibrated prognostics
- **Engine RUL with conformal intervals** — LightGBM quantile regression on NASA C-MAPSS (all four sub-sets, six operating conditions, two fault modes), calibrated by Conformalised Quantile Regression so a "90 % interval" really covers ~90 % of engines. SHAP attributions are mapped to engine modules (Fan / LPC / HPC / HPT / LPT) so the engineer sees *where* the degradation is.
- **LRU survival models** — Weibull accelerated-failure-time models with covariates for **base environment** (dust, heat, humidity, altitude) and **usage severity** (mission g-loading), giving P(failure in next h hours) per installed serial.
- **Logistics-leak detectors** — **No-Fault-Found predictor** (re-test before removal), **rogue-unit detector** (serials that keep failing after repair), **chronic-defect detector** (repeat snags on the same tail and system).

### 2.2 Fleet Twin — a twin of the *sustainment system*
Competitors build a 3D model of one aircraft. TATPAR twins the whole support chain: each tail's state (MC / scheduled maintenance / unscheduled maintenance / awaiting spares / depot), every installed LRU's age, stock at each echelon (squadron → Equipment Depot), the repair pipeline at BRD/HAL with turnaround times, hangar bays and technician capacity. The twin is fast (day-stepped, vectorised), deterministic per seed, and uses common random numbers so policy comparisons are fair.

### 2.3 Prognostics-aware Flight & Maintenance Planning
A constraint-programming model (OR-Tools CP-SAT), inspired by Hellenic/French/Finnish air-force FMP research:
- decides daily flying hours per tail and the start day of each scheduled check;
- respects hangar-bay capacity, check intervals and the daily flying task;
- **staggers** tails along an ideal "phase-flow ladder" so checks never bunch up;
- **bundles** predicted LRU/engine replacements into planned checks (one downtime instead of two);
- caps a tail's flying at the **conformal lower bound** of its RUL unless the replacement is bundled — a risk constraint with a statistical guarantee.

### 2.4 Readiness-Based Sparing with prognostic demand
A two-echelon METRIC/VARI-METRIC model sizes spares at each base and the central depot to **maximise aircraft availability per rupee**, using demand predicted from the survival/prognostic models and the planned flying programme rather than last year's average. A transfer optimiser proposes **lateral moves** ahead of predicted failure spikes, and a **cannibalisation advisor** consolidates robbing onto aircraft that are already down for long periods.

### 2.5 Snag intelligence
Logbook text is normalised (aviation abbreviations, Hinglish), auto-coded to an **ATA chapter**, matched against similar historical cases (MaintNet + fleet history), and the corrective actions are ranked by **fix-effectiveness** (lowest repeat-defect rate).

### 2.6 Data fabric
A common data model aligned to **ASD S5000F** (in-service feedback), **ATA iSpec 2200** (chapters) and **MIMOSA OSA-CBM** (condition-monitoring layers) joins: HUMS/ACMS downloads → tech-log snags → removals & shop findings (incl. NFF) → IMMOLS-style stock and supply transactions → BRD/HAL repair status → flying programme. Every source has a freshness/completeness/consistency score and lineage.

**Built in the prototype:** a unit feeds its own data for each of the four sources the problem statement names — HUMS downloads, the technical log, IMMOLS stock levels and BRD/HAL repair-order status — through published data contracts ([05 · Data contracts](05-data-contracts.md)). Each upload is checked row by row (types, units, ranges, known tails, serials and stock points, duplicates) and the accepted rows change the live picture: a HUMS download re-predicts that engine's remaining life and the new interval flows into alerts, risk, Monte-Carlo forecasts, engine protection and the planner; stock and repair status change spares availability. Every import is hashed, recorded with the signed-in user and written to the decision ledger. A simulated edge gateway (`python -m tatpar.ingest.gateway`) streams post-flight downloads to show the loop live. *Production path:* map the unit's actual e-MMS, IMMOLS and HUMS-ground-station exports onto these contracts (a column mapping), and carry downloads over MQTT/Kafka instead of HTTP.

### 2.7 Trust & sovereignty
Runs fully offline (Docker, CPU laptop or edge server). Federated learning lets bases improve shared models without moving raw data. Every recommendation needs human approval; approvals go into a hash-chained audit log. Model cards show data provenance and calibration. All demo data is public or synthetic and labelled as such.

## 3. What is unique (vs. the seven public PS-26249 projects)

| Capability | Typical submission | TATPAR |
|---|---|---|
| Objective | Predict which part fails | Deliver N MC aircraft on day D with stated confidence |
| Digital twin | 3D aircraft model | Twin of the sustainment system (aircraft + spares + depots + bays + manpower) |
| RUL | Point estimate, C-MAPSS FD001 | Multi-condition FD001–FD004, conformal intervals, module attribution |
| Scheduling | Task priority / MILP | Prognostics-aware FMP with phase-flow staggering and bundling |
| Spares | Reorder point | Multi-echelon RBS (VARI-METRIC) fed by predicted demand + lateral transfers |
| Leaks | — | NFF, rogue units, cannibalisation consolidation |
| Indian context | — | Base Environmental Severity Index from real CAMS dust data |
| Evaluation | Claimed % | Closed-loop A/B in the twin with hidden ground truth and confidence intervals |
| Sovereignty | Cloud RAG | Offline, federated, human-approved, hash-chained audit |

## 4. Users and their daily workflow

| Persona | 60-second question | Screen |
|---|---|---|
| Station Commander (STN CDR) | Will I meet tomorrow's and next month's task? | 01 State, 02 Planning Cell, 06 After-Action |
| Senior Engineering Officer (SENGO) | Which tails fly, which go in, what to bundle? | 03 Flight Line, 04 Airframe, 07 Tech Log |
| Logistics Officer | What to stock where, what to move, what to expedite? | 05 Stores |
| BRD / Depot Manager | Which repairs add the most readiness? | 05 Stores → depot expedite list |
| Analyst / Auditor | Is the data trustworthy, are the models calibrated? | 08 Proof |

The interface is an **operations room**, not a generic dashboard: a tail-plate state board, a daily serviceability signal in service message format (released with a rubber-stamp approval into the hash-chained ledger), a phase track that shows checks bunching at the hangar, Form-700-style technical-log sheets, a whiteprint condition drawing per aircraft, and a duty-officer teleprinter for questions. Day (paper) theme by default for projection and print; night theme one click away.

## 5. How we measure success (honestly)

The Fleet Twin first generates two years of *history* under today's reactive practice. The analytics learn only from those records. New policies are then compared against the baseline on the same random failures (common random numbers) and reported as differences with 95 % confidence intervals:
- mean MC rate and P(meet daily requirement);
- aircraft-days lost by cause;
- unscheduled maintenance events and cannibalisations;
- spares investment needed for a target availability.

Prediction models are reported with standard metrics (RMSE, NASA score, interval coverage, C-index, F1). **All fleet numbers are on a notional fleet and are not IAF results.**
