import { useState } from "react";
import { Link } from "react-router-dom";
import { PhaseTrack } from "../components/PhaseTrack";
import { Board, Chart, ErrorBox, Loading, Panel } from "../components/ui";
import { fmt, fmtPct, postJSON, useApi } from "../lib/api";
import { endLabel, grid, tooltip, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

const SQNS = ["SQN-A", "SQN-B", "SQN-C", "SQN-D"];
const VIEWS: [string, string][] = [["now", "TODAY"], ["baseline_180d", "+180 D · CURRENT"], ["flow_180d", "+180 D · TATPAR"]];

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
  const rows = (ladder[view] || ladder.now).filter((r: any) => r.squadron === sqn);
  const iv = rows[0]?.interval_fh ?? 200;

  const reopt = async () => {
    setBusy(true);
    try {
      const r = await postJSON("/api/plan/run", { horizon: 30 });
      setData({ plan: r.plan, ladder: { ...ladder, now: r.ladder.now } });
    } finally {
      setBusy(false);
    }
  };

  const H = plan.horizon;
  const days = Array.from({ length: H }, (_, i) => `D+${i}`);
  const capOpt = {
    grid: grid({ top: 14, right: 104, left: 30, bottom: 24 }),
    tooltip: tooltip(t),
    xAxis: { type: "category", data: days, axisLabel: { color: t["ink-3"], interval: 4, fontSize: 10.5, fontFamily: "IBM Plex Mono" }, axisLine: { lineStyle: { color: t.ink } }, axisTick: { show: false } },
    yAxis: yVal(t),
    series: [
      { name: "Capable aircraft", type: "line", step: "middle", data: sp.capable, symbol: "none", lineStyle: { color: t.tat, width: 2 }, itemStyle: { color: t.tat }, endLabel: endLabel(t, () => "CAPABLE", t.tat) },
      { name: "Sorties demanded", type: "line", step: "middle", data: sp.demand, symbol: "none", lineStyle: { color: t["ink-2"], width: 1.5, type: [4, 3] }, itemStyle: { color: t["ink-2"] }, endLabel: endLabel(t, () => "TASK", t["ink-2"]) },
      { name: "Sorties short", type: "bar", barMaxWidth: 8, data: sp.short, itemStyle: { color: t.crit } },
    ],
  };
  const engineRisk = sp.tails.filter((r: any) => r.engine_cap_fh != null && r.engine_cap_fh < r.residual_fh);

  return (
    <Board no="03" title="Flight line" sub="Who flies how much, and when each aircraft goes into its phase check. CP-SAT plans the next 30 days for each squadron: meet the flying task, respect the single bay, keep aircraft staggered so checks never bunch, and never fly an engine past its calibrated lower-bound life."
      right={<div className="flex flex-wrap gap-1 items-center">
        {SQNS.map((s) => <button key={s} className={`btn ${s === sqn ? "on" : ""}`} onClick={() => setSqn(s)}>{s}</button>)}
        <button className="btn ml-2" onClick={reopt} disabled={busy}>{busy ? "SOLVING…" : "RE-PLAN"}</button>
      </div>}>
      <section className="panel">
        <div className="lp"><span>Phase track — {sqn} · {iv} FH phase · 1 bay</span>
          <span className="meta flex gap-1">{VIEWS.map(([k, v]) => <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)}>{v}</button>)}</span></div>
        <div className="px-3 pt-3">
          <PhaseTrack interval={iv} laneH={56} W={1300} lanes={[{ label: VIEWS.find(([k]) => k === view)![1], rows, ideal: true }]} />
        </div>
        <div className="foot px-3 pb-3 flex flex-wrap gap-x-6">
          <span><span style={{ color: "var(--accent)" }}>▮</span> ideal staggered position for each aircraft</span>
          <span><span style={{ color: "var(--s-nmcms)" }}>✈</span> in the bay now</span>
          <span>Fleet days lost waiting for a bay over 180 days: current {fmtPct(ladder.baseline_180d_wait_share, 1)} · TATPAR {fmtPct(ladder.flow_180d_wait_share, 1)}</span>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] gap-4 mt-4">
        <Panel title={`Flying programme — ${sqn}, next ${H} days`} meta={`CP-SAT ${sp.status} · ${fmt(sp.wall_s, 1)} S`} pad={false}>
          <Programme sp={sp} days={H} />
        </Panel>
        <div className="space-y-4 min-w-0">
          <Panel title="Capacity vs flying task"><Chart option={capOpt} height={210} /></Panel>
          <Panel title="Engine protection" meta="ENGINE LOWER BOUND < HOURS TO PHASE">
            {engineRisk.length === 0 ? <div className="mono text-[12px] ink-3">NIL THIS PERIOD.</div> : (
              <table className="ledger"><thead><tr><th>Tail</th><th className="n">To phase</th><th className="n">Engine LB</th><th className="n">Phase</th></tr></thead>
                <tbody>{engineRisk.map((r: any) => (
                  <tr key={r.tail}><td className="m"><Link to={`/aircraft/${r.tail}`}>{r.tail}</Link></td><td className="n">{fmt(r.residual_fh)} FH</td><td className="n" style={{ color: "var(--crit)" }}>{fmt(r.engine_cap_fh)} FH</td><td className="n">{r.phase_start != null ? `D+${r.phase_start}` : "—"}</td></tr>))}
                </tbody></table>)}
            <div className="foot">Flying is capped at the engine's conformal lower bound and the engine change is bundled into the phase check.</div>
          </Panel>
        </div>
      </div>
    </Board>
  );
}

/** The squadron flying programme as a board: one row per tail, one column per day, mono codes. */
function Programme({ sp, days }: { sp: any; days: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="mono text-[10.5px] border-collapse w-full" style={{ minWidth: 760 }}>
        <thead>
          <tr>
            <th className="text-left px-2 py-1 cond text-[12px] font-semibold" style={{ borderBottom: "2px solid var(--ink)" }}>TAIL</th>
            {Array.from({ length: days }, (_, i) => (
              <th key={i} className="font-normal ink-3 py-1" style={{ borderBottom: "2px solid var(--ink)", borderLeft: i % 7 === 0 ? "1px solid var(--axis)" : undefined }}>{i % 5 === 0 ? i : ""}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sp.tails.map((r: any) => (
            <tr key={r.tail}>
              <td className="px-2 py-[3px] font-semibold whitespace-nowrap" style={{ borderBottom: "1px solid var(--rule-2)" }}><Link to={`/aircraft/${r.tail}`} className="no-underline">{r.tail}</Link></td>
              {r.days.map((k: string, x: number) => {
                const h = sp.hours[r.tail][x];
                const st: React.CSSProperties = { borderBottom: "1px solid var(--rule-2)", borderLeft: x % 7 === 0 ? "1px solid var(--axis)" : undefined, textAlign: "center", width: 22, height: 21 };
                if (k === "phase") return <td key={x} style={{ ...st, background: "var(--s-nmcms)", color: "#fff", fontWeight: 700 }} title={`${r.tail} D+${x}: phase check`}>P</td>;
                if (k === "down") return <td key={x} style={{ ...st, color: "var(--crit)", fontWeight: 700 }} title={`${r.tail} D+${x}: not available`}>×</td>;
                if (k === "fly") return <td key={x} style={{ ...st, background: "var(--inset)", fontWeight: 600 }} title={`${r.tail} D+${x}: fly ${h} FH`}>{Math.round(h)}</td>;
                return <td key={x} style={{ ...st, color: "var(--ink-3)" }} title={`${r.tail} D+${x}: available, not flying`}>·</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="foot px-3 pb-2">Cell: flight hours flown that day · <b style={{ background: "var(--s-nmcms)", color: "#fff", padding: "0 3px" }}>P</b> phase check in the bay · <b style={{ color: "var(--crit)" }}>×</b> not available · · available, not tasked. Weeks ruled every 7 days.</div>
    </div>
  );
}
