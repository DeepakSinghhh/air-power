# Demo script — TATPAR (≈ 5 minutes)

> Record at 1440 × 900, dark theme, persona **Commander**. Speak to the *decision*, not the model.
> Every figure on screen is from the notional fleet unless it is labelled NASA C-MAPSS / MaintNet / CAMS.

## 0 · Hook (0:00–0:25) — Command overview
- "Reported Su-30MKI serviceability has hovered around 50–60 %. Every SIH team can predict a failing part. The commander's question is different: *how many aircraft will I have on day D, and how sure are you?*"
- Point to **Mission-capable now** and the **60-day fan chart**: grey = current practice, blue = with TATPAR.
- "This band is honest: in back-tests the 80 % band contained 84 % of true outcomes."

## 1 · Readiness-backward planning (0:25–1:40) — Readiness planner
- Requirement already loaded: **≥ 9 mission-capable at Sqn A, Jodhpur, D+14 → D+17, flying task × 1.2**.
- "Current practice meets it 12 % of the time." Walk down the bars: flying & maintenance plan → pre-positioned spares → depot expedite → consolidated cannibalisation & No-Fault-Found screening.
- "Each bar is measured on the same random futures, so the gain belongs to that action."
- Open the action list: phase check moved, engines capped at their conformal lower bound, which spares move where.
- Click **Approve as Commander** → "logged in a hash-chained audit trail".

## 2 · Why readiness is lost (1:40–2:30) — Readiness loss
- History waterfall: awaiting spares is the biggest loss; monthly chart shows **readiness waves** every ~9 months.
- "Those waves are phase checks bunching: aircraft converge and queue for the hangar."
- Lever chart: **readiness-based sparing at the same ₹172 crore** +10 pts → but awaiting-bay rises; **phase-flow plan** +10 pts removes it. "Total +20 points (57.7 % → 78.0 %), ≈ 13 more aircraft every day, same fleet, same budget."

## 3 · Fleet flow (2:30–3:10) — Fleet flow & plan
- Toggle the ladder: Today → +180 days current practice (clustered) → +180 days phase-flow (staggered).
- 30-day Gantt solved by CP-SAT in seconds; **Engine protection** table: "HF-114's engine lower bound is ~0 FH — it goes into phase on D+0 and the engine change is bundled."

## 4 · One aircraft (3:10–3:50) — Aircraft health → HF-114
- Zone schematic, then the engine card: RUL with its calibrated 90 % band; SHAP shows **HPC degradation**.
- "Trained on NASA C-MAPSS — RMSE 12.8–14.0 cycles across all four benchmark sets, 90 % coverage after conformal calibration."

## 5 · The leaks (3:50–4:20) — Sustainment
- RBS frontier: same budget, 83 % → 96 % modelled supply availability.
- AOG table: cannibalise from an aircraft that is already down 32 days — never a serviceable one.
- No-Fault-Found hotspots and the rogue-unit list (100 % precision against hidden truth).

## 6 · The technician (4:20–4:45) — Snag intelligence
- Click the Hinglish example "HYD PRESSURE LH SYSTEM MEIN FLUCTUATION…" → ATA 29 at 99 %, similar cases, fix effectiveness, removal decision.

## 7 · Trust & close (4:45–5:00) — Models & trust
- Federated learning: Leh detachment with 8 engines of history — error falls from 37 to ~15 cycles without sharing raw data.
- "Runs fully offline on a laptop or edge server. Public and synthetic data only. TATPAR — *tatpar*, ever-ready."
