import { Board, Chart, ErrorBox, Loading, Panel } from "../components/ui";
import { fmt, fmtPct, useApi } from "../lib/api";
import { endLabel, grid, MONO, tooltip, xCat, yVal } from "../lib/charts";
import { SQN_COLOR, STATE_CODE, STATE_LABEL, stateColor, useTheme } from "../lib/theme";

const SHORT: Record<string, string> = { POSSESSED: "POSSESSED", NMCS: "SPARES", NMCM_U: "RECTIFY", NMCM_S: "SERVICING", DEPOT: "DEPOT", WAIT: "BAY QUEUE", MC: "SERVICEABLE" };

export default function LossPage() {
  const { tokens: t } = useTheme();
  const wf = useApi<any>("/api/waterfall");
  const lv = useApi<any>("/api/levers");
  if (wf.error || lv.error) return <ErrorBox error={(wf.error || lv.error)!} />;
  if (!wf.data || !lv.data) return <Loading />;
  const hist = wf.data.history;

  // 12-month loss waterfall: possessed → losses by cause → serviceable
  const rows = hist.rows;
  let running = rows[0].value;
  const base: number[] = [], vals: number[] = [], colors: string[] = [];
  rows.forEach((r: any, i: number) => {
    if (i === 0) { base.push(0); vals.push(r.value); colors.push(t["ink-3"]); }
    else if (r.key === "MC") { base.push(0); vals.push(r.value); colors.push(stateColor(t, "MC")); }
    else { running += r.value; base.push(running); vals.push(-r.value); colors.push(stateColor(t, r.key)); }
  });
  const wfOpt = {
    grid: grid({ top: 22, left: 52, bottom: 40, right: 10 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => `<b>${fmt(vals[p.dataIndex])}</b> AIRCRAFT-DAYS<br/>${rows[p.dataIndex].label.toUpperCase()}` }),
    xAxis: { type: "category", data: rows.map((r: any) => SHORT[r.key] ?? r.label), axisLabel: { color: t["ink-2"], interval: 0, fontSize: 10, fontFamily: MONO, width: 90, overflow: "none" }, axisLine: { lineStyle: { color: t.ink } }, axisTick: { show: false } },
    yAxis: yVal(t, { axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => `${v / 1000}K` } }),
    series: [
      { type: "bar", stack: "w", data: base, itemStyle: { color: "transparent" }, silent: true, tooltip: { show: false } },
      { type: "bar", stack: "w", barWidth: 30, data: vals.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })), label: { show: true, position: "top", color: t.ink, fontFamily: MONO, fontSize: 11, fontWeight: 600, formatter: (p: any) => fmt(p.value) } },
    ],
  };

  // lever staircase: current practice, then each lever's paired gain, then the total
  const L = lv.data.rows;
  const lvBase: number[] = [], lvVal: number[] = [], lvCol: string[] = [];
  L.forEach((r: any, i: number) => {
    if (i === 0) { lvBase.push(0); lvVal.push(r.mc); lvCol.push(t.cur); }
    else { const prev = L[i - 1].mc; lvBase.push(Math.min(prev, r.mc)); lvVal.push(Math.abs(r.mc - prev)); lvCol.push(r.mc >= prev ? t.tat : t.crit); }
  });
  lvBase.push(0); lvVal.push(L[L.length - 1].mc); lvCol.push(t.tat);
  const names = [...L.map((r: any) => r.label.replace(/^\+ /, "")), "TATPAR (ALL LEVERS)"];
  const lvOpt = {
    grid: grid({ top: 14, left: 262, right: 66, bottom: 24 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => { const i = p.dataIndex; const r = L[Math.min(i, L.length - 1)]; return i === L.length ? `<b>${fmtPct(r.mc, 1)}</b> MC WITH ALL LEVERS` : `<b>${fmtPct(r.mc, 1)}</b> MC${r.delta != null ? `<br/>Δ ${(r.delta * 100).toFixed(1)} ± ${(r.delta_ci * 100).toFixed(1)} PTS` : ""}`; } }),
    xAxis: yVal(t, { min: 0.5, max: 0.82, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: t.grid } } }),
    yAxis: { type: "category", inverse: true, data: names, axisLabel: { color: t["ink-2"], fontSize: 11.5, fontFamily: "IBM Plex Sans", width: 250, overflow: "truncate" }, axisLine: { lineStyle: { color: t.ink } }, axisTick: { show: false } },
    series: [
      { type: "bar", stack: "l", data: lvBase.map((v) => Math.max(v, 0.5)), itemStyle: { color: "transparent" }, silent: true, tooltip: { show: false } },
      { type: "bar", stack: "l", barWidth: 15, data: lvVal.map((v, i) => ({ value: i === 0 || i === lvVal.length - 1 ? v - 0.5 : v, itemStyle: { color: lvCol[i] } })),
        label: { show: true, position: "right", fontFamily: MONO, fontSize: 11, fontWeight: 600, color: t.ink, formatter: (p: any) => {
          const i = p.dataIndex;
          if (i === 0) return fmtPct(L[0].mc, 1);
          if (i === L.length) return fmtPct(L[L.length - 1].mc, 1);
          const d = L[i].mc - L[i - 1].mc;
          return `${d >= 0 ? "+" : "−"}${Math.abs(d * 100).toFixed(1)}`;
        } } },
    ],
  };

  const fw = wf.data.forward;
  const fwOpt = {
    grid: grid({ top: 24, left: 46, bottom: 26, right: 10 }),
    legend: { top: 0, right: 0, icon: "rect", itemWidth: 12, itemHeight: 8, textStyle: { color: t["ink-2"], fontFamily: MONO, fontSize: 10.5 }, data: ["CURRENT PRACTICE", "TATPAR"] },
    tooltip: tooltip(t, { trigger: "axis" }),
    xAxis: { type: "category", data: fw.map((r: any) => STATE_CODE[r.key] ?? r.key), axisLabel: { color: t["ink-2"], fontSize: 10.5, fontFamily: MONO }, axisLine: { lineStyle: { color: t.ink } }, axisTick: { show: false } },
    yAxis: yVal(t, { axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => `${v / 1000}K` } }),
    series: [
      { name: "CURRENT PRACTICE", type: "bar", barMaxWidth: 20, data: fw.map((r: any) => r.baseline), itemStyle: { color: t.cur } },
      { name: "TATPAR", type: "bar", barMaxWidth: 20, data: fw.map((r: any) => r.tatpar), itemStyle: { color: t.tat } },
    ],
  };

  const mon = wf.data.monthly;
  const months = mon.map((m: any) => m.month);
  const sqns = ["SQN-A", "SQN-B", "SQN-C", "SQN-D"];
  const fleetVals = mon.map((m: any) => m.fleet);
  const troughs = fleetVals.map((v: number, i: number) => ({ v, i })).filter(({ v, i }: any) => i > 0 && i < fleetVals.length - 1 && v < fleetVals[i - 1] && v <= fleetVals[i + 1]).sort((a: any, b: any) => a.v - b.v).slice(0, 2);
  const monOpt = {
    grid: grid({ top: 18, right: 64, left: 40, bottom: 26 }),
    tooltip: tooltip(t, { valueFormatter: (v: number) => fmtPct(v) }),
    xAxis: xCat(t, months, { axisLabel: { color: t["ink-3"], interval: 2, fontSize: 10.5, fontFamily: MONO } }),
    yAxis: yVal(t, { min: 0.3, max: 0.9, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => `${Math.round(v * 100)}%` } }),
    series: [
      ...sqns.map((s, i) => ({ name: s, type: "line", data: mon.map((m: any) => m[s]), symbol: "none", lineStyle: { color: SQN_COLOR(t, i), width: 1.5 }, itemStyle: { color: SQN_COLOR(t, i) },
        endLabel: endLabel(t, () => s.replace("SQN-", "SQN "), SQN_COLOR(t, i)), labelLayout: { moveOverlap: "shiftY" } })),
      { name: "FLEET", type: "line", data: fleetVals, symbol: "none", lineStyle: { color: t.ink, width: 2.6 }, itemStyle: { color: t.ink }, endLabel: endLabel(t, () => "FLEET"), labelLayout: { moveOverlap: "shiftY" },
        markPoint: { symbol: "pin", symbolSize: 0, data: troughs.map(({ v, i }: any) => ({ coord: [months[i], v], label: { show: true, formatter: "▼ WAVE", color: t.crit, fontFamily: MONO, fontWeight: 700, fontSize: 10.5, offset: [0, 14] } })) } },
    ],
  };

  return (
    <Board no="06" title="After-action" sub="Where aircraft-days went, and how many each lever recovers. Lever effects are measured over one year on hidden-truth futures with common random numbers, so each step is that lever's own contribution.">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Panel title={`Last 12 months — ${fmtPct(hist.mc_rate)} serviceable`} meta="AIRCRAFT-DAYS · RECORDED HISTORY">
          <Chart option={wfOpt} height={300} />
          <div className="foot">Possessed aircraft-days, minus each cause of unserviceability, leaves serviceable days. Spares dominate.</div>
        </Panel>
        <Panel title={`Lever staircase — ${fmtPct(L[0].mc, 1)} → ${fmtPct(L[L.length - 1].mc, 1)}`} meta={`${lv.data.reps} FUTURES · ≈ +${fmt(lv.data.aircraft_equivalent, 1)} AC DAILY`}>
          <Chart option={lvOpt} height={300} />
          <div className="foot">Total +{(lv.data.total_delta * 100).toFixed(1)} ± {(lv.data.total_ci * 100).toFixed(1)} pts (95 % CI). Sparing alone moves the bottleneck to the hangar; the phase-flow plan clears it.</div>
        </Panel>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
        <Panel title="Next 12 months — aircraft-days lost by cause" meta="FLEET TWIN, 1 YEAR">
          <Chart option={fwOpt} height={220} />
          <table className="ledger mt-1"><thead><tr><th>Cause</th><th className="n">Current</th><th className="n">TATPAR</th><th className="n">Recovered</th></tr></thead>
            <tbody>{fw.map((r: any) => (<tr key={r.key}><td><span className="mono font-semibold mr-2">{STATE_CODE[r.key] ?? r.key}</span>{STATE_LABEL[r.key] ?? r.label}</td><td className="n">{fmt(r.baseline)}</td><td className="n">{fmt(r.tatpar)}</td>
              <td className="n font-bold" style={{ color: r.recovered > 0 ? "var(--good)" : r.recovered < 0 ? "var(--crit)" : undefined }}>{r.recovered > 0 ? "+" : ""}{fmt(r.recovered)}</td></tr>))}</tbody></table>
        </Panel>
        <Panel title="Readiness waves — monthly serviceable rate" meta="24 MONTHS · CURRENT PRACTICE">
          <Chart option={monOpt} height={300} />
          <div className="foot">Under current practice aircraft converge on the same phase-check point and queue for the hangar, so readiness rises and falls in waves (▼). The phase-flow plan keeps the ladder staggered and removes them.</div>
        </Panel>
      </div>
      <Panel title="Lever ledger" meta="Δ = PAIRED DIFFERENCE VS PREVIOUS ROW, 95 % CI" pad={false} className="mt-4">
        <table className="ledger"><thead><tr><th>Policy stack</th><th className="n">Serviceable</th><th className="n">Δ pts</th><th className="n">SPR share</th><th className="n">BAY share</th><th className="n">Sorties short / yr</th></tr></thead>
          <tbody>{L.map((r: any) => (<tr key={r.label}><td>{r.label}</td><td className="n">{fmtPct(r.mc, 1)}</td>
            <td className="n">{r.delta != null ? `${(r.delta * 100).toFixed(1)} ± ${(r.delta_ci * 100).toFixed(1)}` : "—"}</td>
            <td className="n">{fmtPct(r.state_share.NMCS, 1)}</td><td className="n">{fmtPct(r.state_share.WAIT, 1)}</td><td className="n">{fmt(r.sortie_shortfall)}</td></tr>))}</tbody></table>
      </Panel>
    </Board>
  );
}
