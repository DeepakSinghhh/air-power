# Demo script — TATPAR (≈ 5 minutes)

> Record at 1440 × 900, **DAY** theme. Sign in as **STN CDR** (demo PIN 2601). Speak to the *decision*, not the model.
> Every figure on screen is from the notional fleet unless it is labelled NASA C-MAPSS / MaintNet / CAMS.

## 0 · Hook (0:00–0:30) — 01 STATE
- "Reported Su-30MKI serviceability has hovered around 50–60 %. Every SIH team can predict a failing part. The station commander's question is different: *how many aircraft will I have on day D, and how sure are you?*"
- Sweep the **state board**: 64 tail plates, one colour and one code per state. "37 of 64 serviceable. SPR = awaiting spares, the biggest block."
- Point to the **alerts**: HF-114's engine has 5 flight hours left. Then the **outlook**: grey = current practice, blue = with TATPAR. "In back-tests this 80 % band contained 84 % of real outcomes."
- The **signal** is written from the same numbers. Click **RELEASE AS STN CDR**: the stamp lands, and the release is logged in a hash-chained ledger.

## 1 · Readiness-backward planning (0:30–1:45) — 02 PLANNING CELL
- The task reads as one sentence: **SQN-A to hold at least 9 aircraft every day from D+14 to D+17 at 1.2 × flying task**.
- "Current practice meets it 12 % of the time." Walk up the **staircase**: flying & maintenance plan → pre-positioned spares → depot expedite → consolidated cannibalisation & No-Fault-Found screening → 46 %.
- "Each step is measured on the same random futures, so the gain belongs to that action."
- Read the **operation order**: phase checks moved, engines capped at their conformal lower bound, which spares move where. Click **APPROVE**: stamp, ledger entry, and one **order per action** appears in the tracker, routed to its owner (SENGO, LOG OFFR, DEPOT MGR). "Approval is the start of the loop: the logistics officer marks the transfers actioned, and each change is signed into the ledger." 

## 2 · Why readiness is lost (1:45–2:30) — 06 AFTER-ACTION
- Waterfall: awaiting spares is the biggest loss. Readiness **waves** (▼): aircraft converge on the same phase point and queue for the hangar.
- Lever staircase: **readiness-based sparing at the same ₹172 crore** +10 pts, but the queue moves to the hangar; the **phase-flow plan** +10 pts removes it. "57.7 % → 78.1 %, about 13 more aircraft every day, same fleet, same budget." Then the robustness panel: "change any assumption — failure rates, repair times, stock, flying task — and the gain stays between +16 and +26 points."

## 3 · The flight line (2:30–3:10) — 03 FLIGHT LINE
- Phase track: click **TODAY → +180 D · CURRENT** and the aircraft slide into a bunch at the bay; **+180 D · TATPAR** spreads them back over the ideal ticks.
- The CP-SAT flying programme (solved in about a second); engine protection: "HF-114's engine lower bound is ~0 FH, so it goes into phase on D+0 and the engine change is bundled."

## 4 · One aircraft (3:10–3:50) — 04 AIRFRAME → HF-114
- Whiteprint condition drawing: balloon 1 is the port engine, 5 FH left (90 %: 0–22). The trend shows **HPC degradation** (SHAP).
- "Trained on NASA C-MAPSS: RMSE 12.8–14.0 cycles on all four benchmark sets, 90 % coverage after conformal calibration."
- Form-700 tech log underneath: confirmed vs NFF stamps.

## 5 · The leaks (3:50–4:20) — 05 STORES
- Supply chain schematic, then the RBS frontier: same budget, 83 % → 96 % modelled supply availability.
- AOG decision board: rob only an aircraft already down 32 days, never a serviceable one. NFF hotspots and rogue units.

## 6 · The technician (4:20–4:40) — 07 TECH LOG
- The Hinglish entry "HYD PRESSURE LH SYSTEM MEIN FLUCTUATION…" is already coded: **ATA 29** stamp, removal decision, what fixed it before, similar entries from this fleet and MaintNet.

## 7 · Trust & close (4:40–5:00) — 08 PROOF + DUTY OFFR
- Federated learning: the Leh detachment with 8 engines of history falls from 37 to ~15 cycles error without sharing raw data. Decision ledger: **CHAIN VERIFIED**, both approvals from this demo listed.
- Open **DUTY OFFR**, ask "Status of HF-114". "Runs fully offline on a laptop or edge server. Public and synthetic data only. TATPAR — *tatpar*, ever-ready."
