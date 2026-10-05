import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { Card, Chart, ErrorBox, Loading, PageHeader } from "../components/ui";
import { fmt, fmtPct, postJSON, useApi } from "../lib/api";
import { grid, legend, tooltip, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

const SQNS = ["SQN-A", "SQN-B", "SQN-C", "SQN-D"];
const VIEWS: Record<string, string> = { now: "Today", baseline_180d: "+180 days · current practice", flow_180d: "+180 days · phase-flow plan" };

export default function FlowPage() {
  const { tokens: t } = useTheme();
  const { data, error, setData } = useApi<any>("/api/plan");
  const [sqn, setSqn] = useState("SQN-A");
  const [view, setView] = useState("now");
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const plan = data.plan;
  const ladder = data.ladder;
  const sp = plan.squadrons.find((p: any) => p.squadron === sqn);
  const lad = (ladder[view] || ladder.now).filter((r: any) => r.squadron === sqn);
  const iv = lad[0]?.interval_fh ?? 200;

  const reopt = async () => {
    setBusy(true);
    try {
      const r = await postJSON("/api/plan/run", { horizon: 30 });
      setData({ plan: r.plan, ladder: { ...ladder, now: r.ladder.now } });
    } finally {
      setBusy(false);
    }
  };

  const ladderOpt = {
    grid: grid({ top: 40, left: 52, bottom: 46 }),
    legend: legend(t, { data: ["Hours to phase check", "Ideal staggered ladder"] }),
    tooltip: tooltip(t, { trigger: "axis", formatter: (ps: any[]) => `<b>${lad[ps[0].dataIndex].tail}</b><br/>${ps.map((p: any) => `${p.seriesName}: <b>${fmt(p.value, 0)} FH</b>`).join("<br/>")}${lad[ps[0].dataIndex].in_check ? `<br/>In ${lad[ps[0].dataIndex].in_check} check` : ""}` }),
    xAxis: { type: "category", data: lad.map((r: any) => r.tail), axisLabel: { color: t["text-muted"], rotate: 50, fontSize: 10 }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
    yAxis: yVal(t, { name: "Flight hours to phase", max: iv }),
    series: [
      { name: "Hours to phase check", type: "bar", barMaxWidth: 22, data: lad.map((r: any) => ({ value: Math.max(0, r.residual_fh), itemStyle: { color: r.in_check ? t["series-4"] : t["series-1"], borderRadius: [4, 4, 0, 0] } })) },
      { name: "Ideal staggered ladder", type: "line", data: lad.map((r: any) => r.ideal_fh), symbol: "none", lineStyle: { color: t["text-secondary"], width: 2 }, itemStyle: { color: t["text-secondary"] } },
    ],
  };

  const H = plan.horizon;
  const days = Array.from({ length: H }, (_, i) => `D+${i}`);
  const kinds: Record<string, number> = { idle: 0, fly: 1, phase: 2, down: 3 };
  const cells: any[] = [];
  sp.tails.forEach((r: any, y: number) => r.days.forEach((k: string, x: number) => cells.push([x, y, kinds[k], sp.hours[r.tail][x]])));
  const ganttOpt = {
    grid: grid({ top: 30, left: 64, bottom: 36, right: 12 }),
    tooltip: { backgroundColor: t["surface-1"], borderColor: t.grid, textStyle: { color: t["text-primary"], fontSize: 12 },
      formatter: (p: any) => `<b>${sp.tails[p.value[1]].tail}</b> · ${days[p.value[0]]}<br/>${["Available, not flying", "Flying", "Phase check", "Not available"][p.value[2]]}${p.value[3] ? ` · <b>${p.value[3]} FH</b>` : ""}` },
    xAxis: { type: "category", data: days, splitArea: { show: false }, axisLabel: { color: t["text-muted"], interval: 4 }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
    yAxis: { type: "category", data: sp.tails.map((r: any) => r.tail), inverse: true, axisLabel: { color: t["text-secondary"], fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    visualMap: { type: "piecewise", show: true, dimension: 2, orient: "horizontal", top: 0, left: 60, itemWidth: 12, itemHeight: 12, textStyle: { color: t["text-secondary"] },
      pieces: [{ value: 1, label: "Flying", color: t["series-1"] }, { value: 2, label: "Phase check", color: t["series-4"] }, { value: 3, label: "Not available", color: t["series-2"] }, { value: 0, label: "Available", color: t.grid }] },
    series: [{ type: "heatmap", data: cells, itemStyle: { borderColor: t["surface-1"], borderWidth: 2 } }],
  };

  const capOpt = {
    grid: grid({ top: 34 }),
    legend: legend(t, { data: ["Planned capable aircraft", "Sorties demanded", "Sorties short"] }),
    tooltip: tooltip(t),
    xAxis: { type: "category", data: days, axisLabel: { color: t["text-muted"], interval: 4 }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
    yAxis: yVal(t),
    series: [
      { name: "Planned capable aircraft", type: "line", data: sp.capable, symbol: "none", lineStyle: { color: t["series-1"], width: 2 }, itemStyle: { color: t["series-1"] } },
      { name: "Sorties demanded", type: "line", data: sp.demand, symbol: "none", lineStyle: { color: t["text-secondary"], width: 2 }, itemStyle: { color: t["text-secondary"] } },
      { name: "Sorties short", type: "bar", barMaxWidth: 10, data: sp.short, itemStyle: { color: t.critical, borderRadius: [4, 4, 0, 0] } },
    ],
  };

  const engineRisk = sp.tails.filter((r: any) => r.engine_cap_fh != null && r.engine_cap_fh < r.residual_fh);
  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Fleet flow & flight-maintenance plan"
        sub="Who flies how much, and when each aircraft goes into its phase check. CP-SAT optimises the next 30 days per squadron: meet the flying task, respect hangar bays, keep aircraft staggered so checks never bunch up, and never fly an engine past its calibrated lower-bound life."
        right={<div className="flex gap-2 items-center">
          <select className="input" value={sqn} onChange={(e) => setSqn(e.target.value)}>{SQNS.map((s) => <option key={s}>{s}</option>)}</select>
          <button className="btn" onClick={reopt} disabled={busy}><RefreshCw size={14} />{busy ? "Optimising…" : "Re-optimise"}</button>
        </div>} />

      <Card title="Phase-flow ladder" sub="Bars: flight hours left before each aircraft's phase check. A healthy squadron follows the diagonal; clusters mean several aircraft will need the single bay at once."
        right={<div className="flex gap-1">{Object.entries(VIEWS).map(([k, v]) => (
          <button key={k} className="btn" style={view === k ? { borderColor: "var(--brand)" } : undefined} onClick={() => setView(k)}>{v}</button>))}</div>}>
        <Chart option={ladderOpt} height={300} />
        {view !== "now" && (
          <div className="text-[12.5px] secondary mt-1">
            Share of fleet days spent waiting for a bay over these 180 days — current practice <b>{fmtPct(ladder.baseline_180d_wait_share, 1)}</b>, phase-flow plan <b>{fmtPct(ladder.flow_180d_wait_share, 1)}</b>.
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-4">
        <Card title={`30-day plan — ${sp.squadron}`} sub={`Solver ${sp.status} in ${fmt(sp.wall_s, 1)} s. Each cell is one aircraft-day.`}>
          <Chart option={ganttOpt} height={Math.max(360, 22 * sp.tails.length + 70)} />
        </Card>
        <div className="space-y-4">
          <Card title="Capacity vs flying task"><Chart option={capOpt} height={240} /></Card>
          <Card title="Engine protection" sub="Aircraft whose engine lower-bound life is below the hours left to phase: flying is capped and the engine change is bundled into the check.">
            {engineRisk.length === 0 ? <div className="muted text-sm">None this period.</div> : (
              <table className="tbl"><thead><tr><th>Tail</th><th className="text-right">To phase</th><th className="text-right">Engine lower bound</th><th className="text-right">Phase start</th></tr></thead>
                <tbody>{engineRisk.map((r: any) => (
                  <tr key={r.tail}><td>{r.tail}</td><td className="text-right tabular">{fmt(r.residual_fh)} FH</td><td className="text-right tabular">{fmt(r.engine_cap_fh)} FH</td><td className="text-right tabular">{r.phase_start != null ? `D+${r.phase_start}` : "—"}</td></tr>))}
                </tbody></table>)}
          </Card>
        </div>
      </div>
    </div>
  );
}
