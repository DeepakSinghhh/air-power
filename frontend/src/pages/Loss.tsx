import { Card, Chart, ErrorBox, Loading, PageHeader } from "../components/ui";
import { fmt, fmtPct, useApi } from "../lib/api";
import { grid, legend, tooltip, xCat, yVal } from "../lib/charts";
import { SQN_COLOR, STATE_LABEL, stateColor, useTheme } from "../lib/theme";

const SHORT: Record<string, string> = { POSSESSED: "Possessed", NMCS: "Awaiting spares", NMCM_U: "Unscheduled", NMCM_S: "Scheduled", DEPOT: "Depot", WAIT: "Awaiting bay", MC: "Mission capable" };

export default function LossPage() {
  const { tokens: t } = useTheme();
  const wf = useApi<any>("/api/waterfall");
  const lv = useApi<any>("/api/levers");
  if (wf.error || lv.error) return <ErrorBox error={(wf.error || lv.error)!} />;
  if (!wf.data || !lv.data) return <Loading />;
  const hist = wf.data.history;

  // history waterfall: possessed -> losses -> MC (floating bars)
  const rows = hist.rows;
  let running = rows[0].value;
  const base: number[] = [], vals: number[] = [], colors: string[] = [];
  rows.forEach((r: any, i: number) => {
    if (i === 0) { base.push(0); vals.push(r.value); colors.push(t.baseline); }
    else if (r.key === "MC") { base.push(0); vals.push(r.value); colors.push(stateColor(t, "MC")); }
    else { running += r.value; base.push(running); vals.push(-r.value); colors.push(stateColor(t, r.key)); }
  });
  const wfOpt = {
    grid: grid({ top: 16, left: 64, bottom: 44 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => `<b>${fmt(vals[p.dataIndex])}</b> aircraft-days<br/>${rows[p.dataIndex].label}` }),
    xAxis: { type: "category", data: rows.map((r: any) => SHORT[r.key] ?? r.label), axisLabel: { color: t["text-secondary"], interval: 0, fontSize: 11, width: 70, overflow: "break" }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
    yAxis: yVal(t, { name: "Aircraft-days (last 12 months)" }),
    series: [
      { type: "bar", stack: "w", data: base, itemStyle: { color: "transparent" }, silent: true, tooltip: { show: false } },
      { type: "bar", stack: "w", barWidth: 24, data: vals.map((v, i) => ({ value: v, itemStyle: { color: colors[i], borderRadius: 4 } })),
        label: { show: true, position: "top", color: t["text-primary"], fontSize: 11, formatter: (p: any) => fmt(p.value) } },
    ],
  };

  const L = lv.data.rows;
  const lvOpt = {
    grid: grid({ top: 16, left: 260, right: 70, bottom: 24 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => { const r = L[p.dataIndex]; return `<b>${fmtPct(r.mc, 1)}</b> mission-capable${r.delta != null ? `<br/>Δ ${(r.delta * 100).toFixed(1)} ± ${(r.delta_ci * 100).toFixed(1)} pts` : ""}<br/>${r.label}`; } }),
    xAxis: yVal(t, { min: 0.5, max: 0.85, axisLabel: { color: t["text-muted"], formatter: (v: number) => `${Math.round(v * 100)}%` } }),
    yAxis: { type: "category", inverse: true, data: L.map((r: any) => r.label), axisLabel: { color: t["text-secondary"], fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar", barWidth: 16, data: L.map((r: any, i: number) => ({ value: r.mc, itemStyle: { color: i === 0 ? t.baseline : t["series-1"], borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: t["text-primary"], fontSize: 11, formatter: (p: any) => fmtPct(p.value, 1) } }],
  };

  const fw = wf.data.forward;
  const fwOpt = {
    grid: grid({ top: 36, left: 64, bottom: 30 }),
    legend: legend(t, { data: ["Current practice", "TATPAR"] }),
    tooltip: tooltip(t, { trigger: "axis" }),
    xAxis: { type: "category", data: fw.map((r: any) => STATE_LABEL[r.key] ?? r.label), axisLabel: { color: t["text-secondary"], fontSize: 11 }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
    yAxis: yVal(t, { name: "Aircraft-days / year" }),
    series: [
      { name: "Current practice", type: "bar", barMaxWidth: 22, data: fw.map((r: any) => r.baseline), itemStyle: { color: t.baseline, borderRadius: [4, 4, 0, 0] } },
      { name: "TATPAR", type: "bar", barMaxWidth: 22, data: fw.map((r: any) => r.tatpar), itemStyle: { color: t["series-1"], borderRadius: [4, 4, 0, 0] } },
    ],
  };

  const months = wf.data.monthly.map((m: any) => m.month);
  const sqns = ["SQN-A", "SQN-B", "SQN-C", "SQN-D"];
  const monOpt = {
    grid: grid({ top: 36 }),
    legend: legend(t, { data: [...sqns, "Fleet"] }),
    tooltip: tooltip(t, { valueFormatter: (v: number) => fmtPct(v) }),
    xAxis: xCat(t, months, { axisLabel: { color: t["text-muted"], interval: 2 } }),
    yAxis: yVal(t, { min: 0.3, max: 0.85, axisLabel: { color: t["text-muted"], formatter: (v: number) => `${Math.round(v * 100)}%` } }),
    series: [
      ...sqns.map((s, i) => ({ name: s, type: "line", data: wf.data.monthly.map((m: any) => m[s]), symbol: "none", lineStyle: { color: SQN_COLOR(t, i), width: 2 }, itemStyle: { color: SQN_COLOR(t, i) } })),
      { name: "Fleet", type: "line", data: wf.data.monthly.map((m: any) => m.fleet), symbol: "none", lineStyle: { color: t["text-primary"], width: 2 }, itemStyle: { color: t["text-primary"] } },
    ],
  };

  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Readiness loss" sub="Where aircraft-days go, and how many each lever recovers. Lever effects are measured over one year on hidden-truth futures with common random numbers." />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title={`Last 12 months: ${fmtPct(hist.mc_rate)} mission-capable`} sub="Possessed aircraft-days → losses by cause → mission-capable days (recorded history, current practice)">
          <Chart option={wfOpt} height={320} />
        </Card>
        <Card title={`Levers: ${fmtPct(L[0].mc, 1)} → ${fmtPct(L[L.length - 1].mc, 1)}`}
          sub={`Cumulative policy stack, ${lv.data.reps} futures. Total +${(lv.data.total_delta * 100).toFixed(1)} ± ${(lv.data.total_ci * 100).toFixed(1)} pts ≈ ${fmt(lv.data.aircraft_equivalent)} more aircraft daily.`}>
          <Chart option={lvOpt} height={320} />
        </Card>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Aircraft-days by cause — next 12 months" sub="Fixing spares alone moves the bottleneck to the hangar; the phase-flow plan removes it">
          <Chart option={fwOpt} height={300} />
          <table className="tbl mt-2"><thead><tr><th>Cause</th><th className="text-right">Current</th><th className="text-right">TATPAR</th><th className="text-right">Recovered</th></tr></thead>
            <tbody>{fw.map((r: any) => (<tr key={r.key}><td>{STATE_LABEL[r.key] ?? r.label}</td><td className="text-right tabular">{fmt(r.baseline)}</td><td className="text-right tabular">{fmt(r.tatpar)}</td>
              <td className="text-right tabular font-semibold">{r.recovered > 0 ? "+" : ""}{fmt(r.recovered)}</td></tr>))}</tbody></table>
        </Card>
        <Card title="Monthly mission-capable rate (history)" sub="Readiness waves under current practice: aircraft converge on the same phase-check point and queue for the hangar (awaiting-bay peaks at 15 % of the fleet roughly every nine months). The phase-flow plan removes them.">
          <Chart option={monOpt} height={300} />
        </Card>
      </div>
      <Card title="Lever table" sub="Δ is the paired difference against the previous row (95 % CI)">
        <table className="tbl"><thead><tr><th>Policy stack</th><th className="text-right">Mission-capable</th><th className="text-right">Δ</th><th className="text-right">Awaiting spares</th><th className="text-right">Awaiting bay</th><th className="text-right">Sorties short / yr</th></tr></thead>
          <tbody>{L.map((r: any) => (<tr key={r.label}><td>{r.label}</td><td className="text-right tabular">{fmtPct(r.mc, 1)}</td>
            <td className="text-right tabular">{r.delta != null ? `${(r.delta * 100).toFixed(1)} ± ${(r.delta_ci * 100).toFixed(1)}` : "—"}</td>
            <td className="text-right tabular">{fmtPct(r.state_share.NMCS, 1)}</td><td className="text-right tabular">{fmtPct(r.state_share.WAIT, 1)}</td><td className="text-right tabular">{fmt(r.sortie_shortfall)}</td></tr>))}</tbody></table>
      </Card>
    </div>
  );
}
