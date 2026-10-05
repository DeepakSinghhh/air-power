# 01 · Problem Research — SIH 26249 "Air Power: Predictive Maintenance & Fleet Availability"

> Organisation: Ministry of Defence · Department: Defence Services Staff College (DSSC) · Category: Software · Theme: Transportation & Logistics

## 1. The problem, decomposed

The problem statement makes five distinct claims. We treat each as a requirement:

| # | Claim in the PS | What it means operationally | Requirement for our solution |
|---|---|---|---|
| P1 | *Low aircraft availability* | Mission-capable (MC) rate well below what the fleet size suggests | The primary output must be **aircraft available on the day of need**, not model accuracy |
| P2 | *Fragmented and largely reactive maintenance* | Fix-on-fail plus fixed-interval servicing; little condition-based planning | Move from "replace when broken / when due" to "plan around predicted condition" |
| P3 | *Data from HUMS, technical records, spares and maintenance agencies not integrated* | Health data (onboard recorders), tech logs (e-MMS / Form-700-style), spares ERP (IMMOLS), BRD/HAL repair status live in separate silos | A **common data model** joining tail → system → LRU serial → events → spares → repair pipeline |
| P4 | *Delayed fault prediction, avoidable downtime* | Faults are discovered at the flight line; spares are ordered after the failure | Predictions with **lead time and stated confidence**, linked to spares and scheduling |
| P5 | *Sub-optimal utilisation of critical assets* | Some tails over-flown, others idle; checks bunch up; spares sit at the wrong base; cannibalisation | **Fleet-level optimisation** of flying, maintenance and spares positioning |

## 2. Indian Air Force context (open-source)

- **Serviceability gap.** MoD figures reported the Su-30MKI serviceability at ~48 %, later ~55 %; HAL claimed up to ~68 % (Aero India 2017). Western air forces typically generate 80–85 %. In 2014 this meant only ~106 of 193 Su-30MKIs available for war. ([Business Standard](https://www.business-standard.com/article/economy-policy/govt-takes-note-of-su-30mki-s-poor-serviceability-114102300006_1.html), [Broadsword](https://www.ajaishukla.com/2014/10/government-takes-note-of-su-30mkis-poor.html))
- **Why.** Spares dependence on Russia, AL-31FP engine issues in hot/dusty Indian conditions, and depot turnaround. Post-Op Sindoor commentary notes ~40 % of jets unserviceable at any time and serviceability issues on the small AWACS/tanker fleets. ([Swarajya](https://swarajyamag.com/defence/operation-sindoor-showed-the-iafs-strength-but-also-its-blind-spots), [EurAsian Times](https://www.eurasiantimes.com/s0-30mki-fighters-a-prolonged-russia-ukraine-war-could-severely-impact-india/))
- **Maintenance chain.** First/second line at the squadron and station; third/fourth line at **Base Repair Depots** (e.g., **11 BRD Ojhar** — the IAF's fighter repair depot that overhauls Su-30MKI and MiG-29); OEM overhaul at **HAL Nashik** (airframe) and HAL Koraput (engines); engines overhauled roughly every 800–1000 h. ([Defense Mirror](https://defensemirror.com/news/23570/IAF_Base_Repair_Depot_Performs_Complete_Overhaul_of_Sukhoi_Su_30MKI), [Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fhal-overhaul-sukhois-nashik-plant-2209225))
- **Existing digital systems.** **IMMOLS** (Integrated Materials Management On-Line System — spares ERP) and **e-MMS** (electronic Maintenance Management System). CAPS recommends AI demand forecasting on IMMOLS using "historical consumption data, planned flying effort, past lead-time fluctuations" and AI for supply-chain risk. ([CAPS Issue Brief 08/25](https://capssindia.org/wp-content/uploads/2025/05/CAPS_IB_RK_15_5_25.pdf))
- **Direction of travel.** Digital twins, HUMS analytics, predictive rerouting of spares to bases with predicted failure spikes, and **edge AI at forward bases** so classified data does not traverse vulnerable links. ([The Week, Aug 2026](https://www.theweek.in/news/defence/2026/08/03/opinion-or-keeping-iafs-sukhoi-and-tejas-fleets-combat-ready-with-machine-learning.html), [ADU](https://www.aviation-defence-universe.com/iaf-using-ai-for-predictive-maintenance-and-threat-combat-strategies/)) AMCA is specified with AI self-monitoring targeting 75 % fleet availability. ([defence.in](https://defence.in/threads/amca-to-feature-ai-driven-self-monitoring-for-predictive-maintenance-ensuring-75-fleet-availability-for-iaf.16363/))

**Implication:** the binding constraints are *spares and depot pipeline* and *planning*, not just *prediction accuracy*. A solution that only predicts engine RUL does not move availability.

## 3. What other teams have already built for PS 26249

Seven public repositories target this exact PS. We reviewed each so that our idea is genuinely different.

| Project | What it does | Gap |
|---|---|---|
| [NIRANTAR](https://github.com/HemiAmal/NIRANTAR) | Hierarchical Weibull, Kijima repair model, pharmacovigilance-style signal detection, Merkle-signed ledger, "readiness-as-currency", Hindi/Hinglish snag entry, indigenisation ranking | No flight-and-maintenance planning, no multi-echelon sparing model, no probabilistic fleet forecast |
| [AERO-READY](https://github.com/satyaganesh35/aero-ready) | LightGBM/Bi-LSTM RUL on C-MAPSS, SHAP, dependency graph, MILP task scheduling, Poisson spares, RAG copilot, what-if | Point estimates; spares by reorder point; scheduling by priority index |
| [AeroTwin-AI](https://github.com/Diwakar-odds/AeroTwin-AI-SIH26249) | Bi-LSTM + attention on C-MAPSS FD001, 3D Three.js aircraft twin | Single-engine-model focus; deterministic "88.5 %" claim |
| [AirPower](https://github.com/im-yousuf/AIR-POWER) / [SIH_249](https://github.com/qwertypoiuy9/SIH_249-devin) | React dashboards, EWMA/CUSUM detector, data-integration hub, ATA iSpec 2200 / MIMOSA naming | Simulated ML; no optimisation |
| [PREDIX](https://github.com/ans-data-codes/predix-aircraft-predictive-maintenance) | Skeleton pipelines, Streamlit | Early stage |
| [VAYU SEWA](https://github.com/nitinojha-king/VAYU_SEWA) | Next.js dashboards | Heuristic "ML" |

**Saturated features (earn no novelty):** C-MAPSS FD001 RUL, Isolation-Forest/autoencoder anomaly detection, SHAP bars, 3D/SVG aircraft model, role dashboards, RAG chatbot, Poisson reorder points, work-order automation.

## 4. Literature that defines the white space

| Gap | Evidence | Why it matters for P1/P5 |
|---|---|---|
| **Flight & Maintenance Planning (FMP)** — decide which tail flies how much so that phase checks don't bunch up | Kozanidis (Hellenic AF) bi-objective MILP: max available aircraft + residual flight time ([pdf](http://www.pm10.uth.gr/files/FMP_Kozanidis_Skipis.pdf)); Peschiera et al., French AF long-term FMP ([arXiv 2001.09856](https://arxiv.org/pdf/2001.09856)); Mattila & Virtanen, Finnish AF fighters, simulation-optimisation ([SAGE 2014](https://journals.sagepub.com/doi/abs/10.1177/0037549714540008)); receding-horizon multi-year FMP ([arXiv 2609.11710](https://arxiv.org/pdf/2609.11710)); USAF "Time Distribution Inspection / fleet time" as a leading indicator ([DAFI 21-101](https://static.e-publishing.af.mil/production/1/af_a4/publication/dafi21-101/dafi21-101.pdf)) | Availability is lost when many tails are in the hangar at once — a planning problem, not a prediction problem |
| **Calibrated uncertainty for RUL** | LSTM quantile regression + conformal calibration on C-MAPSS ([Sensors 2026](https://doi.org/10.3390/s26072249)) | Commanders need "how sure"; conformal intervals give distribution-free coverage guarantees |
| **Readiness-Based Sparing** | Sherbrooke METRIC / VARI-METRIC multi-echelon availability models ([Oper. Res. 1986](https://pubsonline.informs.org/doi/10.1287/opre.34.2.311)); spares unavailability is the biggest contributor to low operational availability ([IJIE 2020](https://publisher.uthm.edu.my/ojs/index.php/ijie/article/download/6608/3731/26947)) | Sizes stock for *aircraft availability*, not fill-rate; no open-source implementation exists |
| **No-Fault-Found & rogue units** | NFF up to ~70 % of military avionics removals; 20–50 % across aviation; F-16 depot NFF costs > $13 M/yr ([Aerospace 5(2):38](https://doi.org/10.3390/aerospace5020038), [Aviation Today](https://www.aviationtoday.com/2010/02/01/perspectives-finding-no-fault/)) | Every NFF removal consumes a spare and a repair-pipeline slot |
| **Cannibalisation** | ~850,000 cannibalisations in USAF+USN FY1996–2000; GAO recommends criteria and limiting long-grounded donors ([GAO-02-86](https://www.gao.gov/products/gao-02-86)) | Consolidating cannibalisation onto already-down aircraft preserves availability |
| **Harsh environments** | Desert dust can reduce engine reliability by up to ~50 %; erosion and turbine accretion ([DST-TR-3367](https://www.dst.defence.gov.au/sites/default/files/publications/documents/DST-Group-TR-3367.pdf), [JoA 2023](https://doi.org/10.2514/1.C038359)) | IAF operates from Thar desert, Himalayan high-altitude, coastal-saline and humid NE bases |
| **Federated prognostics** | Collaborative RUL without sharing raw data ([arXiv 2506.00499](https://arxiv.org/pdf/2506.00499)); robust/personalised FL against heterogeneity and poisoning ([arXiv 2608.04045](https://arxiv.org/html/2608.04045)) | Bases keep classified data local; edge AI vision of IAF |
| **Logbook NLP** | MaintNet aviation logbook corpus (6,169 problem/action records) and abbreviation lists ([arXiv 2005.12443](https://arxiv.org/pdf/2005.12443)); KG + LLM fault diagnosis ([Springer 2025](https://link.springer.com/article/10.1007/s42401-025-00412-7)) | Snag text is the richest unstructured source in e-MMS |

## 5. Public datasets we use (no classified data)

| Dataset | Use | Source |
|---|---|---|
| NASA C-MAPSS FD001–FD004 | Engine RUL with multiple operating conditions & fault modes | [NASA PCoE](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) |
| NASA N-CMAPSS (DS02) | Optional Colab upgrade: real flight profiles, module health parameters | [Data 6(1):5](https://www.mdpi.com/2306-5729/6/1/5) |
| MaintNet aviation logbook + abbreviations | Snag normalisation, similar-case retrieval, fix recommendation | [MaintNet](https://people.rit.edu/fa3019/MaintNet/) |
| CAMS dust / AOD via Open-Meteo Air-Quality API | Base Environmental Severity Index for 5 Indian bases | [Open-Meteo](https://open-meteo.com/en/docs/air-quality-api) |
| Synthetic notional fleet (ours) | Logistics, maintenance, spares, depot pipeline with hidden ground truth | Generated — clearly labelled notional |

## 6. Conclusions that drive the design

1. **Optimise availability directly.** Prediction is an input; the product is a plan that keeps N aircraft ready.
2. **Model the sustainment system, not just the aircraft.** Spares, depots, bays and manpower decide whether a prediction turns into availability.
3. **Be honest about uncertainty.** Calibrated intervals and probabilistic forecasts beat confident point numbers in front of a military jury.
4. **Fix the leaks** — NFF, rogue units, cannibalisation — which competitors ignore.
5. **Respect Indian conditions and sovereignty** — environmental severity, offline/edge, federated learning, human approval.
