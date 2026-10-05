// Builds the 6-slide SIH 2026 idea deck for TATPAR (PS 26249).
// Usage: npm install pptxgenjs react-icons react react-dom sharp && node build_deck.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const OUT = path.join(__dirname, "TATPAR_SIH26249_Idea.pptx");
const ARCH_PNG = path.join(__dirname, "..", "architecture.png");
const APPLY_THEME = process.env.APPLY_THEME_JS;

const THEME = {
  name: "TATPAR Readiness",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B1B33", lt1: "FFFFFF", dk2: "1E3A5F", lt2: "EEF3F8",
    accent1: "E8871E", accent2: "0F766E", accent3: "3B82C4",
    accent4: "7C3AED", accent5: "B45309", accent6: "64748B",
    hlink: "2563EB", folHlink: "7C3AED",
  },
};
const HEX = THEME.colors;

async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color: "#" + color, size: String(size) })
  );
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "TATPAR — SIH 2026 PS 26249";
  pres.author = "TATPAR team";
  const C = pres.SchemeColor;

  const footer = (dark) => ({
    text: {
      text: "SIH 2026  ·  PS 26249  ·  TATPAR — Readiness Assurance for Air Fleets",
      options: { x: 0.5, y: 7.0, w: 9, h: 0.3, fontSize: 10, color: dark ? C.background2 : C.accent6, margin: 0 },
    },
  });

  pres.defineSlideMaster({
    title: "TITLE_DARK",
    background: { color: C.text1 },
    objects: [],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: C.background1 },
    margin: [0.5, 0.5, 0.6, 0.5],
    objects: [
      footer(false),
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 12.33, h: 0.8, fontSize: 36, bold: true, color: C.text1, align: "left", valign: "middle", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
  });
  pres.defineSlideMaster({
    title: "CONTENT_DARK",
    background: { color: C.text1 },
    margin: [0.5, 0.5, 0.6, 0.5],
    objects: [
      footer(true),
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 12.33, h: 0.8, fontSize: 36, bold: true, color: C.background1, align: "left", valign: "middle", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.background2, align: "right" },
  });

  const card = (slide, name, x, y, w, h, fill = C.background2) =>
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name,
    });
  const iconCircle = async (slide, name, Comp, x, y, d, bg, fg) => {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg, width: 0 }, objectName: name + "-circle" });
    const pad = d * 0.24;
    slide.addImage({ data: await icon(Comp, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad, objectName: name + "-icon" });
  };

  // ───────────── Slide 1 · Title ─────────────
  pres.addSection({ title: "Title" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Title" });
  s.addText("SMART INDIA HACKATHON 2026", {
    x: 0.6, y: 0.55, w: 7, h: 0.4, fontSize: 14, bold: true, color: C.accent1, charSpacing: 4, margin: 0, isTextBox: true, objectName: "event",
  });
  s.addText("TATPAR", { x: 0.6, y: 1.25, w: 7, h: 1.3, fontFace: THEME.headFontFace, fontSize: 80, bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: "product-name" });
  s.addText([{ text: "तत्पर", options: { color: C.accent1 } }, { text: "  ·  “ever-ready”", options: { color: C.background2 } }], {
    x: 0.6, y: 2.55, w: 7, h: 0.5, fontSize: 22, margin: 0, isTextBox: true, objectName: "meaning",
  });
  s.addText("Readiness Assurance Platform for Air Fleets", {
    x: 0.6, y: 3.2, w: 7.2, h: 1.05, fontSize: 28, bold: true, color: C.accent3, margin: 0, isTextBox: true, objectName: "subtitle",
  });
  s.addText("Others predict failures. TATPAR assures readiness.", {
    x: 0.6, y: 4.35, w: 7.2, h: 0.5, fontSize: 20, italic: true, color: C.background2, margin: 0, isTextBox: true, objectName: "tagline",
  });
  await iconCircle(s, "jet", fa.FaFighterJet, 0.6, 5.35, 1.1, C.accent1, HEX.dk1);
  s.addText("AI prognostics  ·  sustainment digital twin  ·  fleet optimisation  ·  offline & sovereign", {
    x: 1.95, y: 5.55, w: 5.8, h: 0.7, fontSize: 14, color: C.background2, margin: 0, valign: "middle", isTextBox: true, objectName: "pillars",
  });

  card(s, "info-card", 8.2, 0.55, 4.6, 6.2, C.text2);
  const rows = [
    ["Problem Statement ID", "26249"],
    ["Problem Statement Title", "Air Power – Predictive Maintenance & Fleet Availability"],
    ["Organisation", "Ministry of Defence · Defence Services Staff College"],
    ["Theme", "Transportation & Logistics"],
    ["PS Category", "Software"],
    ["Team ID", "To be filled"],
    ["Team Name", "To be filled"],
  ];
  const rowH = [0.62, 0.95, 0.95, 0.62, 0.62, 0.62, 0.62];
  let ry = 0.85;
  rows.forEach(([k, v], i) => {
    s.addText(
      [
        { text: k.toUpperCase(), options: { fontSize: 10, bold: true, color: C.accent1, charSpacing: 1, breakLine: true } },
        { text: v, options: { fontSize: 15, color: C.background1, bold: i < 2 } },
      ],
      { x: 8.5, y: ry, w: 4.05, h: rowH[i], margin: 0, valign: "top", isTextBox: true, objectName: "info-" + i }
    );
    ry += rowH[i] + 0.1;
  });
  s.addNotes("Title slide in the SIH template order. Fill Team ID and Team Name before exporting to PDF.");

  // ───────────── Slide 2 · Proposed solution ─────────────
  pres.addSection({ title: "Solution" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Solution" });
  s.addText("Proposed Solution", { placeholder: "title" });
  s.addText(
    "TATPAR joins health monitoring, technical records, spares and repair-agency data, then plans flying, maintenance and spares so that the required number of aircraft is mission-capable on the day of need — with stated confidence.",
    { x: 0.5, y: 1.12, w: 12.33, h: 0.7, fontSize: 15, color: C.accent6, margin: 0, isTextBox: true, objectName: "lede" }
  );
  const qs = [
    [fa.FaChartArea, C.accent2, "“How many aircraft on day D — and how sure?”", "Readiness Forecast",
      "A Fleet Twin of aircraft, spares, BRD/HAL repair pipeline, bays and manpower runs 200 Monte-Carlo futures → P10–P90 aircraft per day and P(meet task)."],
    [fa.FaBullseye, C.accent1, "“What must I do today to have N ready?”", "Readiness-Backward Planner",
      "Optimises flying hours per tail, check timing, spares transfers, depot priority and cannibalisation; shows each action’s readiness gain; a human approves."],
    [fa.FaChartBar, C.accent4, "“Where is readiness lost — and why?”", "Readiness-Loss Waterfall",
      "Aircraft-days lost to spares, scheduled and unscheduled work, depot and manpower, with the days each lever could recover."],
  ];
  let qy = 2.0;
  for (const [ic, col, q, cap, desc] of qs) {
    card(s, "q-card", 0.5, qy, 7.6, 1.5);
    await iconCircle(s, "q", ic, 0.75, qy + 0.3, 0.9, col, HEX.lt1);
    s.addText(
      [
        { text: q, options: { fontSize: 15, italic: true, color: C.accent6, breakLine: true } },
        { text: cap, options: { fontSize: 18, bold: true, color: C.text1, breakLine: true } },
        { text: desc, options: { fontSize: 13, color: C.text2 } },
      ],
      { x: 1.9, y: qy + 0.1, w: 6.0, h: 1.3, margin: 0, valign: "middle", isTextBox: true, objectName: "q-text" }
    );
    qy += 1.65;
  }
  card(s, "unique-card", 8.4, 2.0, 4.43, 4.8, C.text1);
  s.addText("What is unique", { x: 8.7, y: 2.15, w: 3.9, h: 0.5, fontSize: 20, bold: true, color: C.accent1, margin: 0, isTextBox: true, objectName: "unique-head" });
  const uniq = [
    ["Twin of the sustainment system", " — not a 3D model of one aircraft"],
    ["Calibrated RUL", " — conformal 90 % intervals + engine-module attribution"],
    ["Prognostics-aware flight & maintenance planning", " — staggered checks, bundled repairs"],
    ["Multi-echelon spares (VARI-METRIC)", " fed by predicted demand"],
    ["No-Fault-Found, rogue-unit & cannibalisation", " analytics"],
    ["Indian base environment severity", " from real dust data; offline & federated"],
  ];
  s.addText(
    uniq.flatMap(([b, r], i) => [
      { text: b, options: { bold: true, color: C.background1, bullet: true } },
      { text: r, options: { color: C.background2, breakLine: i < uniq.length - 1 } },
    ]),
    { x: 8.7, y: 2.75, w: 3.95, h: 3.9, fontSize: 14, margin: 0, paraSpaceAfter: 9, valign: "top", isTextBox: true, objectName: "unique-list" }
  );
  s.addNotes("Every other PS-26249 team answers 'which aircraft might fail'. TATPAR answers the three commander questions.");

  // ───────────── Slide 3 · Technical approach ─────────────
  pres.addSection({ title: "Approach" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Approach" });
  s.addText("Technical Approach", { placeholder: "title" });
  s.addImage({ path: ARCH_PNG, x: 0.5, y: 1.2, w: 8.25, h: 4.9, objectName: "architecture" });
  card(s, "stack-card", 9.0, 1.2, 3.83, 4.9);
  s.addText("Technology stack", { x: 9.2, y: 1.3, w: 3.5, h: 0.45, fontSize: 18, bold: true, color: C.text1, margin: 0, isTextBox: true, objectName: "stack-head" });
  const stack = [
    ["Prognostics", "LightGBM quantile + conformal (CQR), SHAP, Weibull AFT (lifelines)"],
    ["Twin & optimisation", "NumPy Monte-Carlo Fleet Twin, OR-Tools CP-SAT, VARI-METRIC"],
    ["Platform", "FastAPI · React + TypeScript · ECharts · SQLite → Postgres/TimescaleDB"],
    ["Data", "NASA C-MAPSS, MaintNet logbooks, CAMS dust, notional synthetic fleet"],
    ["Deploy", "Docker, fully offline on CPU laptop / edge server"],
  ];
  s.addText(
    stack.flatMap(([k, v], i) => [
      { text: k, options: { bold: true, color: C.accent2, fontSize: 13, breakLine: true } },
      { text: v, options: { color: C.text2, fontSize: 13, breakLine: i < stack.length - 1 } },
    ]),
    { x: 9.2, y: 1.8, w: 3.5, h: 4.2, margin: 0, paraSpaceAfter: 4, valign: "top", isTextBox: true, objectName: "stack-list" }
  );
  const steps = ["Integrate", "Predict", "Simulate", "Optimise", "Approve", "Learn"];
  const sw = 2.0, sx0 = 0.5, gap = 0.066;
  steps.forEach((t, i) => {
    s.addShape(i === 0 ? pres.shapes.PENTAGON : pres.shapes.CHEVRON, {
      x: sx0 + i * (sw + gap), y: 6.3, w: sw, h: 0.55,
      fill: { color: i === 4 ? C.accent1 : C.text2 }, line: { color: i === 4 ? C.accent1 : C.text2, width: 0 }, objectName: "step-" + t,
    });
    s.addText(t, { x: sx0 + i * (sw + gap) + 0.25, y: 6.3, w: sw - 0.5, h: 0.55, fontSize: 14, bold: true, color: i === 4 ? C.text1 : C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "step-label-" + t });
  });
  s.addNotes("Six layers: data fabric, intelligence, fleet twin, decision engines, experience, trust. The loop ends with human approval and learning from outcomes.");

  // ───────────── Slide 4 · Feasibility ─────────────
  pres.addSection({ title: "Feasibility" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Feasibility" });
  s.addText("Feasibility & Viability", { placeholder: "title" });
  const stats = [
    ["+20 pts", "mission-capable in the working prototype’s Fleet Twin: 57.7 → 78.0 %, same fleet and spares budget (notional data)"],
    ["90 %", "calibrated engine-RUL interval coverage on NASA C-MAPSS test sets (82.7 % before conformal calibration)"],
    ["0", "cloud dependencies — runs air-gapped on a CPU laptop or edge server; public + synthetic data only"],
  ];
  let sy = 1.3;
  stats.forEach(([big, lab], i) => {
    card(s, "stat-" + i, 0.5, sy, 3.9, 1.72);
    s.addText(big, { x: 0.75, y: sy + 0.12, w: 3.4, h: 0.7, fontSize: 36, bold: true, color: i === 0 ? C.accent2 : C.accent1, margin: 0, isTextBox: true, objectName: "stat-big-" + i });
    s.addText(lab, { x: 0.75, y: sy + 0.82, w: 3.45, h: 0.82, fontSize: 13, color: C.text2, margin: 0, valign: "top", isTextBox: true, objectName: "stat-label-" + i });
    sy += 1.84;
  });
  const hdr = (t) => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 }, fontSize: 13 } });
  const risks = [
    ["No access to real IAF data", "Public datasets + synthetic fleet with hidden ground truth; adapters for IMMOLS / e-MMS exports"],
    ["Trust in AI recommendations", "Calibrated intervals, explanations, human approval, hash-chained audit log"],
    ["Classified, air-gapped networks", "Fully offline; federated learning shares only model weights"],
    ["Legacy and paper records", "Common data model (S5000F / ATA), CSV adapters, data-quality scores"],
    ["Optimisation run-time", "CP-SAT plans a squadron in ~1–2 s; rolling horizon, per-squadron decomposition"],
  ];
  s.addTable(
    [[hdr("Challenge / risk"), hdr("Mitigation built into TATPAR")],
      ...risks.map(([a, b], i) => [
        { text: a, options: { bold: true, color: HEX.dk1, fill: { color: i % 2 ? HEX.lt1 : HEX.lt2 } } },
        { text: b, options: { color: HEX.dk2, fill: { color: i % 2 ? HEX.lt1 : HEX.lt2 } } },
      ])],
    { x: 4.7, y: 1.3, w: 8.13, colW: [2.6, 5.53], fontSize: 12, fontFace: "Calibri", rowH: 0.44, border: { type: "solid", pt: 0.5, color: "D5DEE8" }, valign: "middle", margin: 0.06, objectName: "risk-table" }
  );
  const shots = [["shot-state.png", "01 State board + daily signal"], ["shot-planner.png", "02 Planning cell (P(meet) staircase)"], ["shot-aircraft.png", "04 Airframe: drawing + engine RUL"]];
  shots.forEach(([f, cap], i) => {
    const x = 4.7 + i * 2.765;
    s.addImage({ path: path.join(__dirname, f), x, y: 4.25, w: 2.6, h: 1.625, objectName: "shot-" + i });
    s.addText(cap, { x, y: 5.92, w: 2.6, h: 0.3, fontSize: 11, color: C.accent6, margin: 0, isTextBox: true, objectName: "shot-cap-" + i });
  });
  s.addText([
    { text: "Working prototype built. ", options: { bold: true, color: C.text1 } },
    { text: "Path to deployment: SIH prototype → pilot on one squadron’s historical exports → BRD + IMMOLS integration → command-wide rollout.", options: { color: C.text2 } },
  ], { x: 4.7, y: 6.3, w: 8.13, h: 0.55, fontSize: 12, margin: 0, valign: "top", isTextBox: true, objectName: "path" });
  s.addNotes("Feasible today: every building block exists in open-source tooling; the novelty is in combining them around readiness.");

  // ───────────── Slide 5 · Impact ─────────────
  pres.addSection({ title: "Impact" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Impact" });
  s.addText("Impact & Benefits", { placeholder: "title" });
  const big3 = [
    ["~40 %", "of fighters reported unserviceable at any time (post-Op Sindoor commentary)", C.accent1],
    ["20–70 %", "of military avionics removals end as No-Fault-Found — wasted spares and repair slots", C.accent4],
    ["≈ 13", "more aircraft mission-capable every day from a 64-aircraft fleet in the prototype twin — same spares budget (notional data)", C.accent2],
  ];
  big3.forEach(([n, l, col], i) => {
    const x = 0.5 + i * 4.18;
    card(s, "impact-" + i, x, 1.25, 3.97, 1.75);
    s.addText(n, { x: x + 0.25, y: 1.33, w: 3.5, h: 0.75, fontSize: 40, bold: true, color: col, margin: 0, isTextBox: true, objectName: "impact-big-" + i });
    s.addText(l, { x: x + 0.25, y: 2.08, w: 3.55, h: 0.85, fontSize: 13, color: C.text2, margin: 0, valign: "top", isTextBox: true, objectName: "impact-label-" + i });
  });
  s.addText("Who benefits", { x: 0.5, y: 3.25, w: 5, h: 0.45, fontSize: 18, bold: true, color: C.text1, margin: 0, isTextBox: true, objectName: "who-head" });
  const who = [
    [fa.FaUserTie, "Commander", "N aircraft on day D, with a stated confidence"],
    [fa.FaTools, "Squadron Engineering Officer", "Which tails fly, which go in, what to bundle"],
    [fa.FaTruck, "Logistics Officer", "What to stock, move or expedite — and where"],
    [fa.FaIndustry, "BRD / Depot", "Which repairs add the most readiness first"],
  ];
  let wy = 3.8;
  for (const [ic, r, b] of who) {
    await iconCircle(s, "who", ic, 0.5, wy, 0.55, C.text2, HEX.lt1);
    s.addText([{ text: r, options: { bold: true, color: C.text1, breakLine: true } }, { text: b, options: { color: C.text2 } }], {
      x: 1.2, y: wy - 0.05, w: 4.9, h: 0.65, fontSize: 13, margin: 0, valign: "middle", isTextBox: true, objectName: "who-text",
    });
    wy += 0.77;
  }
  card(s, "benefit-card", 6.4, 3.25, 6.43, 3.55);
  const ben = [
    [fa.FaPlaneDeparture, "Operational", "More aircraft from the same fleet; surge plans with known odds"],
    [fa.FaRupeeSign, "Economic", "Spares bought for availability per rupee; fewer NFF and repeat repairs"],
    [fa.FaFlag, "Strategic", "Sovereign, offline software; supply-risk visibility for indigenisation"],
    [fa.FaShieldAlt, "Safety & people", "Fewer cannibalisations; chronic defects caught early"],
  ];
  let by = 3.45;
  for (const [ic, h, t] of ben) {
    await iconCircle(s, "ben", ic, 6.65, by, 0.55, C.accent1, HEX.dk1);
    s.addText([{ text: h, options: { bold: true, color: C.text1, breakLine: true } }, { text: t, options: { color: C.text2 } }], {
      x: 7.35, y: by - 0.05, w: 5.3, h: 0.7, fontSize: 13, margin: 0, valign: "middle", isTextBox: true, objectName: "ben-text",
    });
    by += 0.82;
  }
  s.addNotes("The first two figures are from open sources (see references). The third is measured in the TATPAR prototype on a notional fleet: +20.3 ± 0.5 points over one year, 24 hidden-truth futures.");

  // ───────────── Slide 6 · References ─────────────
  pres.addSection({ title: "References" });
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "References" });
  s.addText("Research & References", { placeholder: "title" });
  const refCols = [
    ["IAF context", [
      "Business Standard (2014) — Su‑30MKI serviceability 48–55 %",
      "CAPS Issue Brief 08/25 — AI in IAF logistics, IMMOLS, e-MMS",
      "The Week (Aug 2026) — ML for Sukhoi and Tejas fleets, edge AI",
      "Defense Mirror — 11 BRD Ojhar Su‑30MKI overhaul",
    ]],
    ["Operations research", [
      "Kozanidis — Flight & maintenance planning, Hellenic AF",
      "Peschiera et al. — Long-term FMP, French AF (arXiv 2001.09856)",
      "Mattila & Virtanen (2014) — Fighter maintenance sim-optimisation",
      "Sherbrooke — VARI-METRIC, Operations Research (1986)",
      "GAO-02-86 — Military aircraft cannibalisations",
    ]],
    ["Prognostics & AI", [
      "Saxena et al. (2008) — NASA C-MAPSS turbofan dataset",
      "LSTM quantile + conformal RUL — Sensors 26(7) 2249 (2026)",
      "Federated RUL prognostics — arXiv 2506.00499",
      "MaintNet aviation logbooks — COLING 2020",
      "DST-Group-TR-3367 — dust-driven engine degradation",
    ]],
  ];
  refCols.forEach(([h, items], i) => {
    const x = 0.5 + i * 4.18;
    card(s, "ref-card-" + i, x, 1.3, 3.97, 4.0, C.text2);
    s.addText(h, { x: x + 0.25, y: 1.45, w: 3.5, h: 0.45, fontSize: 18, bold: true, color: C.accent1, margin: 0, isTextBox: true, objectName: "ref-head-" + i });
    s.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })), {
      x: x + 0.25, y: 2.0, w: 3.55, h: 3.2, fontSize: 14, color: C.background1, margin: 0, paraSpaceAfter: 8, valign: "top", isTextBox: true, objectName: "ref-list-" + i,
    });
  });
  s.addText(
    [
      { text: "Gap analysis: ", options: { bold: true, color: C.accent1 } },
      { text: "7 public PS-26249 projects reviewed (NIRANTAR, AERO-READY, AeroTwin-AI, AirPower, PREDIX, VAYU SEWA) — none model flight & maintenance planning, multi-echelon sparing or probabilistic readiness. Prototype figures use a notional fleet; no classified data.", options: { color: C.background2 } },
    ],
    { x: 0.5, y: 5.6, w: 12.33, h: 0.9, fontSize: 14, margin: 0, valign: "top", isTextBox: true, objectName: "gap-note" }
  );
  s.addNotes("Full link list in docs/01-research.md.");

  await pres.writeFile({ fileName: OUT });
  if (APPLY_THEME) {
    const { applyTheme } = require(APPLY_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log("wrote", OUT);
})();
