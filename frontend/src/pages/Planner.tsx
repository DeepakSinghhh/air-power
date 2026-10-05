import { useEffect, useState } from "react";
import { dtg, usePersona } from "../components/Layout";
import { Board, Chart, ErrorBox, Loading, Panel } from "../components/ui";
import { fmt, fmtPct, postJSON, useApi } from "../lib/api";
import { endLabel, fanSeries, grid, tooltip, xCat, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

const SQNS = ["SQN-A", "SQN-B", "SQN-C", "SQN-D"];

export default function PlannerPage() {
  const { persona } = usePersona();
  const demo = useApi<any>("/api/requirement/demo");
  const [res, setRes] = useState<any>(null);
  const [form, setForm] = useState({ sqn: "SQN-A", start: 14, end: 17, min_mc: 9, surge: 1.2, reps: 80 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [approved, setApproved] = useState<any>(null);
  useEffect(() => {
    if (demo.data && !res) setRes(demo.data);
  }, [demo.data]);

  const run = async () => {
    setBusy(true);
    setErr(null);
    setApproved(null);
    try {
      setRes(await postJSON("/api/requirement", form));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    const final = res.steps[res.steps.length - 1];
    const e = await postJSON("/api/approve", {
      persona, kind: "readiness_plan",
      summary: `${res.squadron}: ≥${res.min_mc} MC ${res.window.start_date}→${res.window.end_date}; P(meet) ${fmtPct(res.steps[0].p_meet)} → ${fmtPct(final.p_meet)}`,
      payload: { requirement: { squadron: res.squadron, window: res.window, min_mc: res.min_mc, surge: res.surge },
                 actions: res.steps.map((s: any) => ({ lever: s.lever, gain: s.gain, details: s.details.length })) },
    });
    setApproved({ ...e, dtg: dtg(new Date()) });
  };

  if (demo.error) return <ErrorBox error={demo.error} />;
  if (!res) return <Loading />;
  const steps = res.steps;
  const first = steps[0];
  const last = steps[steps.length - 1];
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: k === "sqn" ? e.target.value : Number(e.target.value) });

  return (
    <Board no="02" title="Planning cell" sub="State the requirement; TATPAR works backwards from it. Every action is scored by Monte-Carlo in the Fleet Twin on the same random futures, so each step shows that action's own contribution.">
      <section className="panel">
        <div className="lp"><span>Requirement</span><span className="meta">EDIT THE BLUE FIELDS, THEN PLAN</span></div>
        <div className="pad flex flex-wrap items-center gap-x-2 gap-y-3 text-[17px] leading-relaxed">
          <span className="cond font-semibold text-[18px]">TASK:</span>
          <select className="inline-field" value={form.sqn} onChange={set("sqn")} aria-label="Squadron">{SQNS.map((s) => <option key={s}>{s}</option>)}</select>
          <span>to hold at least</span>
          <input className="inline-field w-[46px]" type="number" min={1} max={16} value={form.min_mc} onChange={set("min_mc")} aria-label="Minimum mission-capable" />
          <span>aircraft mission-capable every day from D+</span>
          <input className="inline-field w-[46px]" type="number" min={0} max={40} value={form.start} onChange={set("start")} aria-label="From day" />
          <span>to D+</span>
          <input className="inline-field w-[46px]" type="number" min={0} max={45} value={form.end} onChange={set("end")} aria-label="To day" />
          <span>at</span>
          <input className="inline-field w-[54px]" type="number" min={0.5} max={2} step={0.1} value={form.surge} onChange={set("surge")} aria-label="Flying task multiplier" />
          <span>× flying task. Test on</span>
          <input className="inline-field w-[54px]" type="number" min={20} max={200} step={20} value={form.reps} onChange={set("reps")} aria-label="Futures" />
          <span>futures.</span>
          <button className="btn ink ml-2" onClick={run} disabled={busy}>{busy ? "PLANNING… ~10 S" : "PLAN"}</button>
          {err && <span className="mono text-[12px]" style={{ color: "var(--crit)" }}>{err}</span>}
        </div>
      </section>

      <div className={`grid grid-cols-1 xl:grid-cols-[1.15fr_1fr] gap-4 mt-4 ${busy ? "opacity-50" : ""}`}>
        <Panel title={`Probability of meeting the task: ${fmtPct(first.p_meet)} → ${fmtPct(last.p_meet)}`} meta={`${res.reps} FUTURES · ${res.window.start_date} → ${res.window.end_date}`}>
          <Staircase steps={steps} />
          <div className="foot">Each tread is P(at least {res.min_mc} MC on every day of the window) after adding that action to all before it. Same random futures for every step.</div>
        </Panel>
        <Panel title={`${res.squadron} readiness forecast`} meta="MEDIAN + P10–P90">
          <Fan res={res} />
        </Panel>
      </div>

      <section className="panel mt-4 relative">
        <div className="lp"><span>Operation order — recommended actions</span><span className="meta">APPROVAL IS WRITTEN TO THE HASH-CHAINED LEDGER</span></div>
        <div className="pad mono text-[12.5px] leading-[1.6]">
          <div className="mb-2"><b>SITUATION.</b> {res.squadron_name.toUpperCase()}. ON CURRENT PRACTICE P(MEET) {fmtPct(first.p_meet)}; MEAN {fmt(first.mean_mc_window, 1)} AC MC IN WINDOW AGAINST {res.min_mc} REQUIRED.</div>
          <div className="mb-1"><b>EXECUTION.</b></div>
          {steps.slice(1).map((s: any, i: number) => (
            <div key={s.lever} className="mb-2 pl-[26px] -indent-[26px]">
              <span>{i + 1}.  </span><b>{s.label.toUpperCase()}.</b>{" "}
              P(MEET) → {fmtPct(s.p_meet)} (<span style={{ color: s.gain >= 0 ? "var(--good)" : "var(--crit)", fontWeight: 600 }}>{s.gain >= 0 ? "+" : ""}{(s.gain * 100).toFixed(0)} PTS</span>). MEAN MC {fmt(s.mean_mc_window, 1)}.
              <Details d={s.details} />
            </div>
          ))}
          <div className="mt-3 flex flex-wrap items-end justify-between gap-4 min-h-[86px]">
            <div><b>COMMAND.</b> FOR APPROVAL BY {persona}.</div>
            {approved ? (
              <span className="stamp big red thump mr-6">
                <b>APPROVED</b><span>{persona} · {approved.dtg}</span><span>LEDGER #{approved.seq} · {approved.hash.slice(0, 8)}</span>
              </span>
            ) : (
              <button className="btn ink" onClick={approve}>APPROVE AS {persona}</button>
            )}
          </div>
        </div>
      </section>
    </Board>
  );
}

/** P(meet) staircase: one tread per action, climbing left to right. */
function Staircase({ steps }: { steps: any[] }) {
  const W = 640, H = 250, x0 = 30, x1 = W - 10, y0 = 18, y1 = H - 62;
  const n = steps.length;
  const wStep = (x1 - x0) / n;
  const Y = (p: number) => y1 - p * (y1 - y0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Probability of meeting the requirement after each action">
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <g key={p}>
          <line x1={x0} x2={x1} y1={Y(p)} y2={Y(p)} stroke="var(--grid)" />
          <text x={x0 - 6} y={Y(p) + 4} textAnchor="end" className="mono" fontSize="10" fill="var(--ink-3)">{p * 100}</text>
        </g>
      ))}
      <line x1={x0} x2={x1} y1={y1} y2={y1} stroke="var(--ink)" />
      {steps.map((s, i) => {
        const x = x0 + i * wStep;
        const y = Y(s.p_meet);
        const col = i === 0 ? "var(--cur)" : "var(--tat)";
        const words: string[] = s.label.toUpperCase().split(" ");
        const lines: string[] = [];
        words.forEach((w) => (lines.length && (lines[lines.length - 1] + " " + w).length <= 18 ? (lines[lines.length - 1] += " " + w) : lines.push(w)));
        return (
          <g key={s.lever}>
            <rect x={x + 2} y={y} width={wStep - 4} height={y1 - y} fill={col} opacity={i === 0 ? 0.22 : 0.12 + (0.5 * i) / n} />
            <line x1={x + 2} x2={x + wStep - 2} y1={y} y2={y} stroke={col} strokeWidth="3" />
            {i > 0 && <line x1={x + 2} x2={x + 2} y1={Y(steps[i - 1].p_meet)} y2={y} stroke={col} strokeWidth="1.5" strokeDasharray="3 2" />}
            <text x={x + wStep / 2} y={y - 6} textAnchor="middle" className="mono" fontSize="13" fontWeight="700" fill="var(--ink)">{Math.round(s.p_meet * 100)}%</text>
            {lines.slice(0, 3).map((l, j) => (
              <text key={j} x={x + wStep / 2} y={y1 + 14 + j * 12} textAnchor="middle" className="cond" fontSize="11.5" fontWeight="600" fill="var(--ink-2)">{l}</text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

function Fan({ res }: { res: any }) {
  const { tokens: t } = useTheme();
  const first = res.steps[0], last = res.steps[res.steps.length - 1];
  const H = first.bands.p50.length;
  const days = Array.from({ length: H }, (_, i) => `D+${i}`);
  const opt = {
    grid: grid({ top: 16, right: 118, bottom: 26, left: 32 }),
    tooltip: tooltip(t, {
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex;
        return `<b>${days[i]}</b><br/>CURRENT ${first.bands.p50[i].toFixed(0)} (${first.bands.p10[i].toFixed(0)}–${first.bands.p90[i].toFixed(0)})<br/>WITH ACTIONS ${last.bands.p50[i].toFixed(0)} (${last.bands.p10[i].toFixed(0)}–${last.bands.p90[i].toFixed(0)})`;
      },
    }),
    xAxis: xCat(t, days, { axisLabel: { color: t["ink-3"], interval: 3, fontSize: 10.5 } }),
    yAxis: yVal(t, { min: 0, max: 16, interval: 4 }),
    series: [
      ...fanSeries("Current practice", t.cur, first.bands, "a", endLabel(t, (v) => `CURRENT ${Math.round(v)}`, t["ink-2"]), true),
      ...fanSeries("With actions", t.tat, last.bands, "b", endLabel(t, (v) => `WITH ACTIONS ${Math.round(v)}`, t.tat)),
      {
        name: "Requirement", type: "line", data: days.map((_, i) => (i >= res.window.start && i <= res.window.end ? res.min_mc : null)), symbol: "none",
        lineStyle: { color: t.crit, width: 2.5 }, itemStyle: { color: t.crit },
        markArea: { silent: true, itemStyle: { color: t.crit, opacity: 0.06 }, data: [[{ xAxis: days[res.window.start] }, { xAxis: days[res.window.end] }]] },
        markPoint: { symbol: "rect", symbolSize: 0, data: [{ coord: [days[res.window.start], res.min_mc], label: { show: true, formatter: `TASK ≥ ${res.min_mc}`, color: t.crit, fontFamily: "IBM Plex Mono", fontWeight: 700, fontSize: 11, offset: [24, -10] } }] },
      },
    ],
  };
  return <Chart option={opt} height={262} />;
}

function Details({ d }: { d: any[] }) {
  if (!d.length) return null;
  const by: Record<string, any[]> = {};
  d.forEach((x) => (by[x.type] = [...(by[x.type] || []), x]));
  const lines: string[] = [];
  if (by.phase) lines.push(`PHASE CHECKS: ${by.phase.map((x) => `${x.tail} AT ${x.phase_start}`).join(" · ")}`);
  if (by.engine_protect) lines.push(`ENGINE PROTECTION (FLY ≤ CONFORMAL LOWER BOUND UNTIL SWAP): ${by.engine_protect.map((x) => `${x.tail} (${String(x.reason).toUpperCase()})`).join(" · ")}`);
  if (by.transfer) lines.push(`TRANSFERS: ${by.transfer.map((x) => `${x.qty}× ${x.name.toUpperCase()} ${String(x.from).toUpperCase()}→${String(x.to).toUpperCase()}`).join(" · ")}`);
  if (by.expedite) lines.push(`EXPEDITE: ${by.expedite.map((x) => `${x.name.toUpperCase()} S/N ${x.serial} (${x.agency}, DUE ${x.return_in_days} D)`).join(" · ")}`);
  if (by.policy) lines.push(`POLICY: ${by.policy.map((x) => x.text.toUpperCase()).join(" · ")}`);
  return (
    <div className="ink-2 text-[11.5px] mt-0.5">
      {lines.map((l, i) => <div key={i} className="pl-[22px] -indent-[22px]">({String.fromCharCode(97 + i)}) {l}</div>)}
    </div>
  );
}
