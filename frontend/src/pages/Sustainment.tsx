import { useState } from "react";
import { Card, Chart, ErrorBox, Loading, PageHeader, Stat } from "../components/ui";
import { fmt, fmtPct, title, useApi } from "../lib/api";
import { grid, legend, tooltip, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

export default function SustainmentPage() {
  const { tokens: t } = useTheme();
  const { data, error } = useApi<any>("/api/sustainment");
  const [demand, setDemand] = useState<"prognostic" | "historical">("prognostic");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const rbs = data.rbs[demand];
  const backorders = Object.values(data.backorders as Record<string, number>).reduce((a, b) => a + b, 0);
  const pipeUnits = data.pipeline.reduce((a: number, p: any) => a + p.qty, 0);
  const transit = Object.values(data.in_transit as Record<string, number>).reduce((a, b) => a + b, 0);

  const curve = rbs.curve;
  const frontierOpt = {
    grid: grid({ top: 40, left: 56, bottom: 40 }),
    legend: legend(t, { data: ["RBS frontier", "Current allocation", "RBS at same budget"] }),
    tooltip: { trigger: "item", backgroundColor: t["surface-1"], borderColor: t.grid, textStyle: { color: t["text-primary"], fontSize: 12 },
      formatter: (p: any) => `<b>${fmtPct(p.value[1], 1)}</b> supply availability<br/>₹${fmt(p.value[0] / 100, 0)} crore inventory` },
    xAxis: { type: "value", name: "Spares inventory (₹ crore)", nameLocation: "middle", nameGap: 26, axisLabel: { color: t["text-muted"], formatter: (v: number) => fmt(v / 100) }, splitLine: { lineStyle: { color: t.grid } }, axisLine: { lineStyle: { color: t.axis } }, nameTextStyle: { color: t["text-muted"] } },
    yAxis: yVal(t, { name: "Supply availability", min: 0, max: 1, axisLabel: { color: t["text-muted"], formatter: (v: number) => `${v * 100}%` } }),
    series: [
      { name: "RBS frontier", type: "line", data: curve.map((c: any) => [c.cost_lakh, c.availability]), symbol: "none", lineStyle: { color: t["series-1"], width: 2 }, itemStyle: { color: t["series-1"] } },
      { name: "Current allocation", type: "scatter", symbolSize: 12, data: [[rbs.budget_lakh, rbs.availability_current]], itemStyle: { color: t.baseline, borderColor: t["surface-1"], borderWidth: 2 } },
      { name: "RBS at same budget", type: "scatter", symbolSize: 12, data: [[rbs.budget_lakh, rbs.availability_rbs]], itemStyle: { color: t["series-1"], borderColor: t["surface-1"], borderWidth: 2 } },
    ],
  };
  const nffTop = data.nff.slice(0, 12);
  const nffOpt = {
    grid: grid({ left: 190, top: 8, right: 50, bottom: 24 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => `<b>${fmtPct(p.value)}</b> No-Fault-Found<br/>${p.name}` }),
    xAxis: yVal(t, { max: 0.8, axisLabel: { color: t["text-muted"], formatter: (v: number) => `${Math.round(v * 100)}%` } }),
    yAxis: { type: "category", inverse: true, data: nffTop.map((r: any) => r.name), axisLabel: { color: t["text-secondary"], fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar", barWidth: 14, data: nffTop.map((r: any) => ({ value: r.nff_rate, itemStyle: { color: t["series-2"], borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: t["text-secondary"], fontSize: 11, formatter: (p: any) => fmtPct(p.value) } }],
  };
  const changed = rbs.table.filter((r: any) => r.rbs_total !== r.current_total).sort((a: any, b: any) => (b.rbs_total - b.current_total) - (a.rbs_total - a.current_total));
  const adv = data.advisors;

  return (
    <div className="space-y-4 max-w-[1500px]">
      <PageHeader title="Sustainment" sub="Spares across echelons (squadron stores → central depot → BRD / HAL repair), readiness-based sparing, and the leaks that drain the pipeline: No-Fault-Found removals, rogue units and cannibalisation." />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Open part demands (AOG)" value={fmt(backorders)} sub="aircraft positions awaiting a part" />
        <Stat label="Units in repair pipeline" value={fmt(pipeUnits)} sub="at BRD / HAL" />
        <Stat label="Units in transit" value={fmt(transit)} sub="depot ↔ bases" />
        <Stat label="RBS supply availability" value={`${fmtPct(rbs.availability_current)} → ${fmtPct(rbs.availability_rbs)}`} sub={`same ₹${fmt(rbs.budget_lakh / 100)} crore budget`} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_1fr] gap-4">
        <Card title="Readiness-based sparing (two-echelon VARI-METRIC)"
          sub="Spares sized for aircraft availability per rupee rather than fill rate. Demand from the prognostic models for the planned flying, or from last year's history."
          right={<select className="input" value={demand} onChange={(e) => setDemand(e.target.value as any)}><option value="prognostic">Prognostic demand</option><option value="historical">Historical demand</option></select>}>
          <Chart option={frontierOpt} height={300} />
        </Card>
        <Card title="Rebalanced stock levels" sub="Total units per part type (depot + bases): current vs RBS at the same budget">
          <div className="scroll-y max-h-[310px]">
            <table className="tbl">
              <thead><tr><th>Part</th><th className="text-right">Demand / month</th><th className="text-right">Repair TAT</th><th className="text-right">Current</th><th className="text-right">RBS</th><th className="text-right">Δ</th></tr></thead>
              <tbody>{changed.map((r: any) => (
                <tr key={r.lru}><td>{r.name}<div className="muted text-[11px]">₹{fmt(r.cost_lakh, 1)} lakh</div></td><td className="text-right tabular">{fmt(r.demand_per_month, 1)}</td>
                  <td className="text-right tabular">{fmt(r.tat_days)} d</td><td className="text-right tabular">{r.current_total}</td><td className="text-right tabular">{r.rbs_total}</td>
                  <td className="text-right tabular font-semibold" style={{ color: r.rbs_total > r.current_total ? "var(--success-text)" : "var(--critical)" }}>{r.rbs_total > r.current_total ? "+" : ""}{r.rbs_total - r.current_total}</td></tr>))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card title="Aircraft on ground — part decisions" sub="Wait, move a spare laterally, or cannibalise — preferring donors that are already grounded longest (consolidation), never a serviceable aircraft.">
        <div className="scroll-y max-h-[340px]">
          <table className="tbl">
            <thead><tr><th>Tail</th><th>Missing part</th><th className="text-right">Down</th><th className="text-right">ETA</th><th>Source</th><th>Lateral</th><th>Donors</th><th>Recommendation</th></tr></thead>
            <tbody>{adv.cannibalisation.map((r: any, i: number) => (
              <tr key={i}><td><b>{r.tail}</b><div className="muted text-[11px]">{r.squadron}</div></td><td>{r.name}</td><td className="text-right tabular">{r.down_days} d</td><td className="text-right tabular">{r.eta_days} d</td>
                <td className="secondary">{r.source}</td><td className="secondary">{r.lateral_options.map(title).join(", ") || "—"}</td>
                <td className="secondary">{r.donors.map((d: any) => `${d.tail} (${d.down_days} d)`).join(", ") || "—"}</td><td>{r.recommendation}</td></tr>))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Predictive transfers — next 14 days" sub="Move spares to where the models expect failures (z = 1 safety margin)">
          <div className="scroll-y max-h-[320px]">
            <table className="tbl"><thead><tr><th>Part</th><th>From</th><th>To</th><th className="text-right">Qty</th><th className="text-right">Expected demand</th></tr></thead>
              <tbody>{adv.transfers.map((m: any, i: number) => (
                <tr key={i}><td>{m.name}</td><td>{title(m.from)}</td><td>{title(m.to)}</td><td className="text-right tabular">{m.qty}</td><td className="text-right tabular">{fmt(m.expected_demand, 2)}</td></tr>))}
              </tbody></table>
          </div>
        </Card>
        <Card title="Depot expedite list" sub="Repairs whose early return adds the most readiness">
          <table className="tbl"><thead><tr><th>Part</th><th>Serial</th><th>Agency</th><th className="text-right">Due in</th><th className="text-right">Priority</th></tr></thead>
            <tbody>{adv.expedite.map((r: any) => (
              <tr key={r.serial}><td>{r.name}</td><td className="tabular">{r.serial}</td><td>{r.agency}</td><td className="text-right tabular">{r.return_in_days} d</td><td className="text-right tabular">{fmt(r.priority, 1)}</td></tr>))}
            </tbody></table>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="No-Fault-Found hotspots (last 12 months)" sub="Share of removals the shop found serviceable — each one consumed a spare and a repair slot">
          <Chart option={nffOpt} height={320} />
        </Card>
        <Card title="Rogue units" sub="Serials whose lives after repair are repeatedly far shorter than the fleet model predicts — quarantine / deep-strip">
          <div className="scroll-y max-h-[320px]">
            <table className="tbl"><thead><tr><th>Serial</th><th>Part</th><th className="text-right">Confirmed removals</th><th className="text-right">Median life</th><th className="text-right">vs fleet</th><th>Last tail</th></tr></thead>
              <tbody>{data.rogue.map((r: any) => (
                <tr key={r.serial}><td className="tabular">{r.serial}</td><td>{r.name}</td><td className="text-right tabular">{r.removals}</td><td className="text-right tabular">{fmt(r.median_life_h)} FH</td>
                  <td className="text-right tabular">{fmtPct(r.life_ratio)}</td><td>{r.last_tail}</td></tr>))}
              </tbody></table>
          </div>
        </Card>
      </div>
    </div>
  );
}
