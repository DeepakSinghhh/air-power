import { useState } from "react";
import { Link } from "react-router-dom";
import { dataDtg, dtg, usePersona } from "../components/Layout";
import { PhaseTrack } from "../components/PhaseTrack";
import { Chart } from "../components/Chart";
import { Board, ErrorBox, Loading, Panel, StateLegend } from "../components/ui";
import { fmt, fmtPct, postJSON, useApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { endLabel, fanSeries, grid, tooltip, xCat, yVal } from "../lib/charts";
import { STATE_CODE, stateCss, useTheme } from "../lib/theme";

const sqnShort = (name: string) => name.split(" (")[0].toUpperCase();
const sqnBase = (name: string) => (name.split("— ")[1] ?? "").toUpperCase();

export default function Overview() {
  const ov = useApi<any>("/api/overview");
  const fleet = useApi<any[]>("/api/fleet");
  const plan = useApi<any>("/api/plan");
  if (ov.error || fleet.error) return <ErrorBox error={(ov.error || fleet.error)!} />;
  if (!ov.data || !fleet.data) return <Loading />;
  const d = ov.data;
  return (
    <Board no="01" title="State" sub={`Aircraft state at the ${dataDtg(d.today)} parade, what the next 60 days look like, and what needs a decision now. Click any tail for its record.`}>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_440px] gap-4">
        <div className="space-y-4 min-w-0">
          <StateBoard d={d} fleet={fleet.data} />
          <Panel title={`Phase track — ${sqnShort(d.squadrons[0].name)} · 1 bay`} meta="BUNCHING = A READINESS WAVE FORMING" pad={false}>
            <div className="px-3 pt-2 pb-1">
              {plan.data ? <PhaseTrack lanes={[
                { label: "TODAY", rows: plan.data.ladder.now.filter((r: any) => r.squadron === d.squadrons[0].id) },
                { label: "+180 D · CURRENT", rows: plan.data.ladder.baseline_180d.filter((r: any) => r.squadron === d.squadrons[0].id) },
                { label: "+180 D · TATPAR", rows: plan.data.ladder.flow_180d.filter((r: any) => r.squadron === d.squadrons[0].id) },
              ]} /> : <Loading label="PLOTTING" />}
            </div>
            <div className="foot px-3 pb-2 -mt-1">Current practice lets aircraft drift together and queue for the single bay; the TATPAR flight-and-maintenance plan keeps them evenly spaced. Full ladder for every squadron on <Link to="/flow">03 FLIGHT LINE</Link>.</div>
          </Panel>
        </div>
        <div className="space-y-4 min-w-0">
          <Alerts d={d} fleet={fleet.data} />
          <Signal d={d} />
        </div>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_440px] gap-4 mt-4">
        <Outlook d={d} />
        <Environment d={d} />
      </div>
    </Board>
  );
}

function StateBoard({ d, fleet }: { d: any; fleet: any[] }) {
  return (
    <Panel title="State board — aircraft serviceability" meta={`AS AT ${dataDtg(d.today)}`} pad={false}>
      <div className="flex flex-wrap items-end justify-between gap-3 px-4 pt-2 pb-2 border-b" style={{ borderColor: "var(--rule-2)" }}>
        <div className="flex items-baseline gap-2">
          <span className="cond font-bold text-[50px] leading-[.9]" style={{ letterSpacing: ".01em" }}>{d.mc_now}</span>
          <span className="cond font-semibold text-[24px] ink-3">/{d.n_tails}</span>
          <span className="mono text-[13px] ink-2 ml-2">SERVICEABLE · {fmtPct(d.mc_now / d.n_tails)}</span>
        </div>
        <StateLegend short />
      </div>
      <div className="board">
        {d.squadrons.map((s: any) => {
          const ts = fleet.filter((t) => t.squadron === s.id);
          return (
            <div key={s.id} className="min-w-0">
              <div className="colhead"><span>{sqnShort(s.name)} · {sqnBase(s.name)}</span><b>{s.mc_now}<small>/{s.n}</small></b></div>
              <div className="mono text-[10px] ink-3 -mt-1 mb-1.5" title="Median mission-capable at D+30, current practice → with TATPAR actions">
                D+30 {s.d30_baseline ? fmt(s.d30_baseline[1]) : "—"} → <span style={{ color: "var(--tat)", fontWeight: 600 }}>{s.d30_tatpar ? fmt(s.d30_tatpar[1]) : "—"}</span> WITH ACTIONS
              </div>
              {ts.map((t) => <Plate key={t.tail} t={t} />)}
            </div>
          );
        })}
      </div>
      <div className="foot px-4 pb-2">Plate: state code · tail · bar and figure = flight hours to phase check · <span className="flag-eng">E5</span> engine life below 40 FH · <span className="flag-risk">▲</span> P(snag in 7 days) ≥ 40 %.</div>
    </Panel>
  );
}

function Plate({ t }: { t: any }) {
  const res = Math.max(0, Math.min(200, t.to_phase));
  const eng = t.engine_rul_fh_min;
  return (
    <Link to={`/aircraft/${t.tail}`} className="plate" title={`${t.tail} · ${fmt(t.to_phase)} FH to phase · P(snag 7d) ${fmtPct(t.p_snag_7d)}${eng != null ? ` · engine RUL ${fmt(eng)} FH` : ""}`}>
      <span className="code" style={{ background: stateCss(t.state) }}>{STATE_CODE[t.state]}</span>
      <span className="tl">{t.tail}</span>
      <span className="ph"><i style={{ width: `${res / 2}%` }} /></span>
      <span className="phn">{fmt(res)}</span>
      <span className="flags">
        {eng != null && eng < 40 && <span className="flag-eng">E{fmt(eng)}</span>}
        {t.p_snag_7d >= 0.4 && <span className="flag-risk">▲</span>}
      </span>
    </Link>
  );
}

/** Cockpit-style alert list: warnings, cautions, advisories, status — each line links to the board that resolves it. */
function Alerts({ d, fleet }: { d: any; fleet: any[] }) {
  const ord = useApi<any>("/api/orders");
  type Row = { k: "w" | "c" | "a" | "s"; text: string; val: string; to: string } | null;
  const rows: Row[] = [];
  d.engine_watch.forEach((e: any) => rows.push({ k: e.engine_rul_fh_min < 10 ? "w" : "c", text: `${e.tail} ENG RUL`, val: `${String(Math.round(e.engine_rul_fh_min)).padStart(3, "0")} FH`, to: `/aircraft/${e.tail}` }));
  d.squadrons.filter((s: any) => s.mc_now < 8).forEach((s: any) => rows.push({ k: "c", text: `${sqnShort(s.name)} MC BELOW 50 %`, val: `${String(s.mc_now).padStart(2, "0")}/${s.n}`, to: "/planner" }));
  fleet.filter((t) => t.state === "MC" && t.to_phase > 0 && t.to_phase < 20).sort((a, b) => a.to_phase - b.to_phase).slice(0, 2)
    .forEach((t) => rows.push({ k: "c", text: `${t.tail} PHASE DUE`, val: `${String(Math.round(t.to_phase)).padStart(3, "0")} FH`, to: "/flow" }));
  rows.push({ k: "c", text: "AC AWAITING SPARES", val: String(d.states.NMCS).padStart(2, "0"), to: "/sustainment" });
  rows.push(null);
  rows.push({ k: "a", text: "SPARES TRANSFERS RECOMMENDED", val: String(d.actions.transfers).padStart(2, "0"), to: "/sustainment" });
  rows.push({ k: "a", text: "AOG DEMANDS OPEN", val: String(d.actions.aog).padStart(2, "0"), to: "/sustainment" });
  rows.push({ k: "a", text: "DEPOT REPAIRS TO EXPEDITE", val: String(d.actions.expedite).padStart(2, "0"), to: "/sustainment" });
  if (ord.data?.outstanding) rows.push({ k: "a", text: "ORDERS OUTSTANDING", val: String(ord.data.outstanding).padStart(2, "0"), to: "/planner" });
  rows.push(null);
  const cal = d.forecast.calibration;
  if (cal) rows.push({ k: "s", text: "FORECAST CALIBRATED (80 % BAND)", val: fmtPct(cal.coverage_p10_p90), to: "/proof" });
  if (d.headline.delta != null) rows.push({ k: "s", text: "TATPAR POLICY GAIN / YEAR", val: `+${(d.headline.delta * 100).toFixed(1)} PTS`, to: "/loss" });
  const nw = rows.filter((r) => r?.k === "w").length, nc = rows.filter((r) => r?.k === "c").length;
  return (
    <Panel title="Alerts" meta={<><span style={{ color: nw ? "#ff8a7a" : undefined }}>{nw} WARN</span> · {nc} CAUT</>}>
      <div className="alerts">
        {rows.map((r, i) => r === null ? <div key={i} className="gap" /> : (
          <Link key={i} to={r.to} className={`row ${r.k}`}><span>{r.k === "w" ? "■ " : r.k === "c" ? "▲ " : r.k === "a" ? "◆ " : "● "}{r.text}</span><b>{r.val}</b></Link>
        ))}
      </div>
    </Panel>
  );
}

/** Daily serviceability signal in military message format, composed from the same numbers on this board. */
function Signal({ d }: { d: any }) {
  const { persona } = usePersona();
  const { can } = useAuth();
  const [rel, setRel] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fb = d.forecast.baseline, ft = d.forecast.tatpar, s = d.states, eng = d.engine_watch;
  const weak = [...d.squadrons].sort((a: any, b: any) => a.mc_now - b.mc_now)[0];
  const at = dataDtg(d.today);
  const r0 = (x: number) => Math.round(x);
  const paras = [
    `1. STATE. ${d.mc_now} OF ${d.n_tails} AC MC (${fmtPct(d.mc_now / d.n_tails)}). ${s.NMCS} AWAITING SPARES. ${s.NMCM_U} UNDER RECTIFICATION. ${s.NMCM_S} IN SERVICING. ${s.DEPOT} AT BRD. ${s.WAIT} AWAITING BAY.`,
    fb ? `2. OUTLOOK D+30. ${r0(fb.p50[30])} AC (${r0(fb.p10[30])}–${r0(fb.p90[30])}) ON CURRENT PRACTICE. ${r0(ft.p50[30])} AC (${r0(ft.p10[30])}–${r0(ft.p90[30])}) WITH RECOMMENDED ACTIONS.` : "2. OUTLOOK. NOT AVAILABLE.",
    eng.length >= 2 ? `3. ENGINE WATCH. ${eng[0].tail} RUL ${r0(eng[0].engine_rul_fh_min)} FH. ${eng[1].tail} RUL ${r0(eng[1].engine_rul_fh_min)} FH. RECOMMEND ${eng[0].tail} PHASE + ENG CHANGE D+0.` : "3. ENGINE WATCH. NIL.",
    `4. LOWEST. ${sqnShort(weak.name)} ${weak.mc_now}/${weak.n} MC. ${weak.states.NMCS} AWAITING SPARES.`,
    `5. PENDING. ${d.actions.transfers} SPARES MOVES. ${d.actions.aog} AOG DEMANDS. ${d.actions.expedite} DEPOT EXPEDITES. SEE PLANNING CELL.`,
    `6. ACTION. APPROVE PARAS 3 AND 5.`,
  ];
  const head = [["PRIORITY", "ROUTINE"], ["FM", "TATPAR READINESS CELL"], ["TO", "STN CDR · SENGO ALL SQN"], ["INFO", "HQ MAINT COMD"], ["DTG", at], ["SUBJ", "DAILY SERVICEABILITY STATE + 30-DAY OUTLOOK"]];
  const plain = `UNCLAS — NOTIONAL DATA\n${head.map(([k, v]) => `${k.padEnd(9)}${v}`).join("\n")}\n${"-".repeat(48)}\n${paras.join("\n")}`;
  const copy = () => navigator.clipboard?.writeText(plain);
  const print = () => {
    const w = window.open("", "_blank", "width=720,height=800");
    if (!w) return;
    w.document.write(`<pre style="font:13px/1.6 'IBM Plex Mono',monospace;white-space:pre-wrap;padding:24px">${plain.replace(/</g, "&lt;")}${rel ? `\n\nRELEASED BY ${rel.persona} · ${rel.dtg} · LEDGER #${rel.seq} ${rel.hash.slice(0, 8)}` : ""}</pre>`);
    w.document.close();
    w.print();
  };
  const release = async () => {
    setBusy(true);
    setErr(null);
    try {
      const e = await postJSON<any>("/api/approve", { kind: "daily_signal", summary: `Daily serviceability signal ${at}: ${d.mc_now}/${d.n_tails} MC`, payload: { text: plain } });
      setRel({ ...e, dtg: dtg(new Date()) });
    } catch (x) {
      setErr(String(x));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Signal" pad={false} meta={<><button onClick={copy}>COPY</button> <button onClick={print}>PRINT</button></>}>
      <div className="signal">
        <div className="flex justify-between"><span><b>PRIORITY</b> ROUTINE</span><span><b>UNCLAS</b> · NOTIONAL</span></div>
        {head.slice(1).map(([k, v]) => <div key={k}><b className="inline-block w-[46px]">{k}</b>{v}</div>)}
        <span className="rule" />
        {paras.map((p) => <div key={p} className="pl-[22px] -indent-[22px]">{p}</div>)}
        {err && <div className="mono text-[11px] noprint" style={{ color: "var(--crit)" }}>✕ {err}</div>}
        <div className="relative h-[70px] mt-1">
          <div className="absolute right-2 bottom-2 text-right">
            <div>FOR STN CDR</div>
            <div className="border-t mt-0.5 w-[120px] ml-auto" style={{ borderColor: "var(--ink)" }} />
          </div>
          {rel ? (
            <span className="stamp big red thump absolute left-[60px] top-[4px]">
              <b>RELEASED</b><span>{rel.persona} · {rel.dtg}</span><span>LEDGER #{rel.seq} · {rel.hash.slice(0, 8)}</span>
            </span>
          ) : (
            can("approve:daily_signal")
              ? <button className="btn ink absolute left-0 bottom-2 noprint" onClick={release} disabled={busy}>{busy ? "LOGGING…" : `RELEASE AS ${persona}`}</button>
              : <span className="absolute left-0 bottom-3 mono text-[11px] ink-3">RELEASE: STN CDR / SENGO ONLY</span>
          )}
        </div>
      </div>
    </Panel>
  );
}

function Outlook({ d }: { d: any }) {
  const { tokens: t } = useTheme();
  const fb = d.forecast.baseline, ft = d.forecast.tatpar, cal = d.forecast.calibration;
  if (!fb) return <Panel title="Outlook — 60 days"><Loading /></Panel>;
  const days = fb.p50.map((_: number, i: number) => `D+${i}`);
  const opt = {
    grid: grid({ top: 14, right: 132, bottom: 26, left: 38 }),
    tooltip: tooltip(t, {
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex;
        return `<b>${days[i]}</b><br/>CURRENT ${fb.p50[i].toFixed(0)} (${fb.p10[i].toFixed(0)}–${fb.p90[i].toFixed(0)})<br/>TATPAR ${ft.p50[i].toFixed(0)} (${ft.p10[i].toFixed(0)}–${ft.p90[i].toFixed(0)})`;
      },
    }),
    xAxis: xCat(t, days, { axisLabel: { color: t["ink-3"], interval: 9, fontSize: 10.5 } }),
    yAxis: yVal(t, { min: 20, max: 52, interval: 8 }),
    series: [
      ...fanSeries("Current practice", t.cur, fb, "b", endLabel(t, (v) => `CURRENT ${Math.round(v)}`, t["ink-2"]), true),
      ...fanSeries("With TATPAR", t.tat, ft, "t", endLabel(t, (v) => `WITH TATPAR ${Math.round(v)}`, t.tat)),
    ],
  };
  return (
    <Panel title="Outlook — mission-capable aircraft, next 60 days" meta="MEDIAN + P10–P90 OF 150 SIMULATED FUTURES">
      <Chart option={opt} height={250} />
      <div className="foot">Both forecasts start from today's state and use only model predictions (no hidden truth). {cal && <>Simulated back-test: the 80 % band contained {fmtPct(cal.coverage_p10_p90)} of hidden-truth outcomes. </>}Weekly rhythm = aircraft recovered at weekends.</div>
    </Panel>
  );
}

function Environment({ d }: { d: any }) {
  return (
    <Panel title="Base severity" meta="REAL CAMS 2024 DUST + CLIMATOLOGY">
      <table className="ledger">
        <thead><tr><th>Base</th><th className="n">Dust µg/m³</th><th className="n">Heat</th><th className="n">Hum</th><th className="n">×Sev</th></tr></thead>
        <tbody>
          {d.environment.map((b: any) => (
            <tr key={b.base} title={b.climate}><td className="cond text-[13px]">{b.name}</td><td className="n">{fmt(b.dust_ugm3, 1)}</td><td className="n">{fmt(b.heat, 2)}</td><td className="n">{fmt(b.hum, 2)}</td><td className="n font-semibold">{fmt(b.severity_index, 2)}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="foot">Severity multiplies LRU failure rates in the survival models. Leh is shown for detachment planning.</div>
    </Panel>
  );
}
