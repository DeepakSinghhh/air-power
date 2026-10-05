import { useState } from "react";
import { Link } from "react-router-dom";
import { Board, Chart, ErrorBox, Loading, Meter, Panel } from "../components/ui";
import { fmt, fmtPct, title, useApi } from "../lib/api";
import { grid, MONO } from "../lib/charts";
import { useTheme } from "../lib/theme";

const BASES = ["jodhpur", "pune", "tezpur", "thanjavur"];

export default function SustainmentPage() {
  const { tokens: t } = useTheme();
  const { data, error } = useApi<any>("/api/sustainment");
  const [demand, setDemand] = useState<"prognostic" | "historical">("prognostic");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const rbs = data.rbs[demand];
  const curve = rbs.curve;
  const knee = curve.reduce((a: any, c: any) => (Math.abs(c.cost_lakh - rbs.budget_lakh * 0.5) < Math.abs(a.cost_lakh - rbs.budget_lakh * 0.5) ? c : a), curve[0]);
  const frontierOpt = {
    grid: grid({ top: 16, left: 46, bottom: 40, right: 20 }),
    tooltip: { trigger: "item", backgroundColor: t.panel, borderColor: t.ink, borderRadius: 0, textStyle: { color: t.ink, fontSize: 12, fontFamily: MONO },
      formatter: (p: any) => `<b>${fmtPct(p.value[1], 1)}</b> SUPPLY AVAILABILITY<br/>₹${fmt(p.value[0] / 100, 0)} CR INVENTORY` },
    xAxis: { type: "value", name: "SPARES INVENTORY (₹ CRORE)", nameLocation: "middle", nameGap: 24, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => fmt(v / 100) }, splitLine: { lineStyle: { color: t.grid } }, axisLine: { lineStyle: { color: t.ink } }, nameTextStyle: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5 } },
    yAxis: { type: "value", min: 0, max: 1, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => `${v * 100}%` }, splitLine: { lineStyle: { color: t.grid } } },
    series: [
      { name: "RBS frontier", type: "line", data: curve.map((c: any) => [c.cost_lakh, c.availability]), symbol: "none", lineStyle: { color: t.tat, width: 2 },
        markPoint: { symbol: "rect", symbolSize: 0, data: [{ coord: [knee.cost_lakh, knee.availability], label: { show: true, formatter: "RBS FRONTIER (TWO-ECHELON VARI-METRIC)", color: t.tat, fontFamily: MONO, fontSize: 11, fontWeight: 600, position: "bottom", distance: 14 } }] } },
      { name: "Current allocation", type: "scatter", symbol: "rect", symbolSize: 11, data: [[rbs.budget_lakh, rbs.availability_current]], itemStyle: { color: t.cur, borderColor: t.panel, borderWidth: 2 },
        label: { show: true, position: "right", formatter: `TODAY ${fmtPct(rbs.availability_current)}`, color: t["ink-2"], fontFamily: MONO, fontSize: 11, fontWeight: 600 } },
      { name: "RBS at same budget", type: "scatter", symbol: "rect", symbolSize: 11, data: [[rbs.budget_lakh, rbs.availability_rbs]], itemStyle: { color: t.tat, borderColor: t.panel, borderWidth: 2 },
        label: { show: true, position: "top", distance: 8, formatter: `RBS ${fmtPct(rbs.availability_rbs)}`, color: t.tat, fontFamily: MONO, fontSize: 11, fontWeight: 700 } },
    ],
  };
  const changed = rbs.table.filter((r: any) => r.rbs_total !== r.current_total).sort((a: any, b: any) => (b.rbs_total - b.current_total) - (a.rbs_total - a.current_total));
  const adv = data.advisors;

  return (
    <Board no="05" title="Stores" sub="Spares across echelons — squadron stores, the equipment depot and BRD / HAL repair — sized by readiness-based sparing, and the leaks that drain the pipeline: No-Fault-Found removals, rogue units and cannibalisation.">
      <Panel title="Supply chain — where the spares are" meta="UNITS NOW · FLOWS PER YEAR" pad={false}>
        <Pipeline data={data} rbs={rbs} />
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] gap-4 mt-4">
        <section className="panel">
          <div className="lp"><span>Readiness-based sparing (RBS)</span>
            <span className="meta flex gap-1">{(["prognostic", "historical"] as const).map((k) => <button key={k} className={demand === k ? "on" : ""} onClick={() => setDemand(k)}>{k === "prognostic" ? "PROGNOSTIC" : "HISTORICAL"}</button>)}</span></div>
          <div className="pad">
            <Chart option={frontierOpt} height={270} />
            <div className="foot">Same ₹{fmt(rbs.budget_lakh / 100)} crore budget, stocked for aircraft availability per rupee instead of fill rate: {fmtPct(rbs.availability_current)} → {fmtPct(rbs.availability_rbs)} supply availability.</div>
          </div>
        </section>
        <Panel title="Rebalanced stock levels" meta="DEPOT + BASES, SAME BUDGET" pad={false}>
          <div className="scroll-y max-h-[322px]">
            <table className="ledger">
              <thead><tr><th>Part</th><th className="n">Dem/mo</th><th className="n">TAT</th><th className="n">Now</th><th className="n">RBS</th><th className="n">Δ</th></tr></thead>
              <tbody>{changed.map((r: any) => (
                <tr key={r.lru}><td>{r.name}<span className="mono ink-3 text-[10.5px]"> · ₹{fmt(r.cost_lakh, 1)} L</span></td><td className="n">{fmt(r.demand_per_month, 1)}</td>
                  <td className="n">{fmt(r.tat_days)} D</td><td className="n">{r.current_total}</td><td className="n">{r.rbs_total}</td>
                  <td className="n font-bold" style={{ color: r.rbs_total > r.current_total ? "var(--good)" : "var(--crit)" }}>{r.rbs_total > r.current_total ? "+" : ""}{r.rbs_total - r.current_total}</td></tr>))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <Panel title="AOG decision board — wait, move or rob" meta="ROB ONLY AIRCRAFT ALREADY GROUNDED LONGEST" pad={false} className="mt-4">
        <div className="scroll-y max-h-[340px]">
          <table className="ledger">
            <thead><tr><th>Tail</th><th>Missing part</th><th className="n">Down</th><th className="n">ETA</th><th>Source</th><th>Lateral</th><th>Donors</th><th>Decision</th></tr></thead>
            <tbody>{adv.cannibalisation.map((r: any, i: number) => (
              <tr key={i}><td className="m"><Link to={`/aircraft/${r.tail}`}><b>{r.tail}</b></Link></td><td>{r.name}</td><td className="n">{r.down_days} D</td><td className="n">{r.eta_days} D</td>
                <td className="ink-2">{r.source}</td><td className="ink-2">{r.lateral_options.map(title).join(", ") || "—"}</td>
                <td className="ink-2 mono text-[11.5px]">{r.donors.map((d: any) => `${d.tail} (${d.down_days} D)`).join(", ") || "—"}</td>
                <td><span className="tag" style={{ borderColor: "var(--ink-2)", color: "var(--ink)" }}>{String(r.recommendation).toUpperCase()}</span></td></tr>))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
        <Panel title="Predictive transfers — next 14 days" meta="Z = 1 SAFETY MARGIN" pad={false}>
          <div className="scroll-y max-h-[300px]">
            <table className="ledger"><thead><tr><th>Part</th><th>From → to</th><th className="n">Qty</th><th className="n">Exp. demand</th></tr></thead>
              <tbody>{adv.transfers.map((m: any, i: number) => (
                <tr key={i}><td>{m.name}</td><td className="m">{String(m.from).toUpperCase()} → {String(m.to).toUpperCase()}</td><td className="n">{m.qty}</td><td className="n">{fmt(m.expected_demand, 2)}</td></tr>))}
              </tbody></table>
          </div>
        </Panel>
        <Panel title="Depot expedite list" meta="EARLY RETURN THAT ADDS MOST READINESS" pad={false}>
          <table className="ledger"><thead><tr><th>Part</th><th className="n">S/N</th><th>Agency</th><th className="n">Due</th><th className="n">Priority</th></tr></thead>
            <tbody>{adv.expedite.map((r: any) => (
              <tr key={r.serial}><td>{r.name}</td><td className="n">{r.serial}</td><td className="m">{r.agency}</td><td className="n">{r.return_in_days} D</td><td className="n">{fmt(r.priority, 1)}</td></tr>))}
            </tbody></table>
        </Panel>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
        <Panel title="No-Fault-Found hotspots — 12 months" meta="REMOVALS THE SHOP FOUND SERVICEABLE">
          {data.nff.slice(0, 12).map((r: any) => (
            <div key={r.lru} className="grid grid-cols-[minmax(0,190px)_minmax(0,1fr)_92px] items-center gap-3 py-[3px] border-b" style={{ borderColor: "var(--rule-2)" }}>
              <span className="text-[12.5px] truncate">{r.name}</span>
              <Meter value={r.nff_rate / 0.8} color="var(--s-nmcs)" />
              <span className="mono text-[11.5px] text-right"><b>{fmtPct(r.nff_rate)}</b> <span className="ink-3">{r.nff}/{r.removals}</span></span>
            </div>
          ))}
          <div className="foot">Each NFF removal consumed a spare and a repair slot. TATPAR's NFF model flags likely ones for a ground re-test first (07 TECH LOG).</div>
        </Panel>
        <Panel title="Rogue units" meta="QUARANTINE / DEEP-STRIP" pad={false}>
          <div className="scroll-y max-h-[360px]">
            <table className="ledger"><thead><tr><th className="n">S/N</th><th>Part</th><th className="n">Removals</th><th className="n">Median life</th><th className="n">vs fleet</th><th>Last tail</th></tr></thead>
              <tbody>{data.rogue.map((r: any) => (
                <tr key={r.serial}><td className="n">{r.serial}</td><td>{r.name}</td><td className="n">{r.removals}</td><td className="n">{fmt(r.median_life_h)} FH</td>
                  <td className="n font-bold" style={{ color: "var(--crit)" }}>{fmtPct(r.life_ratio)}</td><td className="m"><Link to={`/aircraft/${r.last_tail}`}>{r.last_tail}</Link></td></tr>))}
              </tbody></table>
          </div>
          <div className="foot px-3 pb-2">Serials whose lives after repair are repeatedly far shorter than the fleet model predicts (Fisher combination of PIT values + life-ratio rule).</div>
        </Panel>
      </div>
    </Board>
  );
}

/** Schematic of the two-echelon pipeline: squadron stores ↔ equipment depot ↔ repair agencies. */
function Pipeline({ data, rbs }: { data: any; rbs: any }) {
  const stockAt = (p: string) => data.stock.filter((s: any) => s.stock_point === p).reduce((a: number, s: any) => a + s.qty, 0);
  const atAgency = (a: string) => data.pipeline.filter((p: any) => p.agency === a).reduce((s: number, p: any) => s + p.qty, 0);
  const flow = (src: string, dst: string) => data.supply_flow.find((f: any) => f.source === src && f.target === dst)?.value ?? 0;
  const aog = Object.values(data.backorders as Record<string, number>).reduce((a, b) => a + b, 0);
  const W = 1000, H = 290;
  const bx = 24, bw = 250, bh = 50, gap = 12, by0 = 24;
  const ex = 440, ew = 180, ey = 92, eh = 92;
  const rx = 770, rw = 200;
  const box = (x: number, y: number, w: number, h: number) => <rect x={x} y={y} width={w} height={h} fill="var(--panel)" stroke="var(--ink)" strokeWidth="1.5" />;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Spares pipeline schematic" className="block">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="var(--ink)" /></marker>
        <marker id="arrR" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="var(--crit)" /></marker>
      </defs>
      {BASES.map((b, i) => {
        const y = by0 + i * (bh + gap);
        const cur = rbs.base_current?.[b], nb = rbs.base_rbs?.[b];
        return (
          <g key={b}>
            {box(bx, y, bw, bh)}
            <text x={bx + 10} y={y + 19} className="cond" fontSize="14" fontWeight="600" fill="var(--ink)">{b.toUpperCase()} STORES</text>
            <text x={bx + 10} y={y + 38} className="mono" fontSize="11" fill="var(--ink-2)">STOCK {stockAt(b)} · IN TRANSIT {data.in_transit[b] ?? 0}</text>
            {cur != null && <text x={bx + bw - 8} y={y + 38} textAnchor="end" className="mono" fontSize="11" fill="var(--tat)" fontWeight="600">{fmtPct(cur)}→{fmtPct(nb)}</text>}
            <line x1={ex} y1={ey + eh / 2} x2={bx + bw + 4} y2={y + bh / 2} stroke="var(--ink)" strokeWidth="1.4" markerEnd="url(#arr)" />
          </g>
        );
      })}
      <text x={bx + bw - 8} y={by0 - 8} textAnchor="end" className="mono" fontSize="10" fill="var(--tat)">SUPPLY AVAIL NOW→RBS</text>
      <text x={(bx + bw + ex) / 2 + 4} y={ey + eh / 2 - 2} textAnchor="middle" className="mono" fontSize="10.5" fill="var(--ink-2)" stroke="var(--panel)" strokeWidth="5" paintOrder="stroke"><tspan x={(bx + bw + ex) / 2 + 4}>SERVICEABLE ISSUES</tspan><tspan x={(bx + bw + ex) / 2 + 4} dy="13">{flow("Equipment depot", "Squadron bases")}/YR</tspan></text>
      {box(ex, ey, ew, eh)}
      <text x={ex + ew / 2} y={ey + 30} textAnchor="middle" className="cond" fontSize="16" fontWeight="700" fill="var(--ink)">EQUIPMENT DEPOT</text>
      <text x={ex + ew / 2} y={ey + 52} textAnchor="middle" className="mono" fontSize="12" fill="var(--ink-2)">STOCK {stockAt("ED")}</text>
      <text x={ex + ew / 2} y={ey + 72} textAnchor="middle" className="mono" fontSize="11" fill="var(--crit)" fontWeight="700">AOG DEMANDS {aog}</text>
      {["BRD", "HAL"].map((a, i) => {
        const y = 40 + i * 92;
        return (
          <g key={a}>
            {box(rx, y, rw, 64)}
            <text x={rx + 12} y={y + 24} className="cond" fontSize="15" fontWeight="700" fill="var(--ink)">{a === "BRD" ? "BRD (IAF REPAIR DEPOT)" : "HAL (OEM REPAIR)"}</text>
            <text x={rx + 12} y={y + 46} className="mono" fontSize="12" fill="var(--ink-2)">IN REPAIR {atAgency(a)} UNITS</text>
            <line x1={rx - 4} y1={y + 32} x2={ex + ew + 4} y2={ey + eh / 2 + (i ? 12 : -12)} stroke="var(--ink)" strokeWidth="1.4" markerEnd="url(#arr)" />
          </g>
        );
      })}
      <text x={(ex + ew + rx) / 2} y={ey + eh / 2 + 4} textAnchor="middle" className="mono" fontSize="10.5" fill="var(--ink-2)" stroke="var(--panel)" strokeWidth="5" paintOrder="stroke">REPAIRED {flow("Repair agencies", "Equipment depot")}/YR</text>
      <path d={`M${bx + bw / 2} ${by0 + 4 * (bh + gap) - gap + 2} L${bx + bw / 2} ${H - 18} L${rx + rw / 2} ${H - 18} L${rx + rw / 2} ${40 + 92 + 64 + 4}`} fill="none" stroke="var(--crit)" strokeWidth="1.4" strokeDasharray="6 4" markerEnd="url(#arrR)" />
      <text x={(bx + rx + rw) / 2 + 40} y={H - 24} textAnchor="middle" className="mono" fontSize="10.5" fill="var(--crit)">UNSERVICEABLE RETURNS {flow("Squadron bases", "Repair agencies")}/YR</text>
    </svg>
  );
}
