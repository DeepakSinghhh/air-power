import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Planform, StateStamp, Stamp, type Balloon } from "../components/glyphs";
import { Chart } from "../components/Chart";
import { Board, Code, ErrorBox, Kv, Loading, Meter, Panel } from "../components/ui";
import { fmt, fmtPct, useApi, useIngestStamp } from "../lib/api";
import { grid, tooltip, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

export default function AircraftPage() {
  const { tail } = useParams();
  const fleet = useApi<any[]>("/api/fleet");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"risk" | "tail" | "phase">("risk");
  const nav = useNavigate();
  const rows = useMemo(() => {
    const r = (fleet.data || []).filter((x) => !q || x.tail.toLowerCase().includes(q.toLowerCase()) || x.squadron.toLowerCase().includes(q.toLowerCase()));
    return [...r].sort((a, b) => sort === "risk" ? b.p_snag_7d - a.p_snag_7d : sort === "phase" ? a.to_phase - b.to_phase : a.tail.localeCompare(b.tail));
  }, [fleet.data, q, sort]);
  if (fleet.error) return <ErrorBox error={fleet.error} />;
  if (!fleet.data) return <Loading />;
  const current = tail ?? [...fleet.data].sort((a, b) => b.p_snag_7d - a.p_snag_7d)[0]?.tail;
  return (
    <Board no="04" title="Airframe" sub="Every tail's state, hours to each check, short-term snag risk and engine remaining life. Select a tail for its condition drawing, engine trend, component record and technical log.">
      <div className="grid grid-cols-1 xl:grid-cols-[400px_minmax(0,1fr)] gap-4 items-start">
        <section className="panel xl:sticky xl:top-[92px]">
          <div className="lp"><span>Register</span>
            <span className="meta flex gap-1">
              <input className="input !py-0 !text-[11px] w-[96px]" style={{ background: "transparent", color: "var(--plate-ink)", borderColor: "#66705f" }} placeholder="FILTER" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter tails" />
              {(["risk", "phase", "tail"] as const).map((s) => <button key={s} className={sort === s ? "on" : ""} onClick={() => setSort(s)}>{s === "risk" ? "RISK" : s === "phase" ? "PHASE" : "TAIL"}</button>)}
            </span></div>
          <div className="scroll-y max-h-[calc(100vh-150px)]">
            <table className="ledger">
              <thead><tr><th>Tail</th><th>St</th><th className="n">To ph</th><th className="n">P(snag)</th><th className="n">Eng RUL</th><th>Flags</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.tail} onClick={() => nav(`/aircraft/${r.tail}`)} style={{ cursor: "pointer" }} className={r.tail === current ? "sel" : ""}>
                    <td className="m"><b>{r.tail}</b> <span className="ink-3 text-[10.5px]">{r.squadron.replace("SQN-", "")}</span></td>
                    <td><Code state={r.state} /></td>
                    <td className="n">{fmt(r.to_phase)}</td>
                    <td className="n" style={{ color: r.p_snag_7d >= 0.4 ? "var(--warn)" : undefined, fontWeight: r.p_snag_7d >= 0.4 ? 700 : 400 }}>{r.p_snag_7d.toFixed(2)}</td>
                    <td className="n" style={{ color: r.engine_rul_fh_min != null && r.engine_rul_fh_min < 40 ? "var(--crit)" : undefined }}>{r.engine_rul_fh_min != null ? fmt(r.engine_rul_fh_min) : "—"}</td>
                    <td className="whitespace-nowrap">{r.chronic && <span className="tag" title="Chronic defect">CHR</span>} {r.rogue_parts > 0 && <span className="tag" title="Rogue unit fitted">ROGUE</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        {current && <Detail tail={current} />}
      </div>
    </Board>
  );
}

const ZONE_XY: Record<number, [number, number]> = {
  34: [200, 64], 31: [200, 118], 25: [200, 132], 23: [206, 150], 27: [330, 384], 28: [118, 340], 29: [218, 300], 24: [182, 280],
  21: [300, 330], 36: [160, 300], 32: [250, 372], 49: [200, 440], 72: [237, 470], 73: [237, 450], 77: [163, 450], 79: [163, 470],
};

function Detail({ tail }: { tail: string }) {
  const seq = useIngestStamp();      // a HUMS download (or any import) refreshes the record
  const { data, error, loading } = useApi<any>(`/api/aircraft/${tail}`, [seq]);
  if (error) return <ErrorBox error={error} />;
  if (!data || data.tail !== tail) return <Panel title={tail}><Loading label="COMPUTING HUMS PREDICTIONS" /></Panel>;
  return (
    <div className={`space-y-4 min-w-0 ${loading ? "opacity-60" : ""}`}>
      <section className="panel">
        <div className="pad flex flex-wrap items-center gap-x-5 gap-y-3">
          <div className="cond font-bold text-[40px] leading-none tracking-[.04em]">{data.tail}</div>
          <StateStamp state={data.state} seed={data.tail} />
          <div className="text-[12.5px] ink-2 leading-snug">{data.type_label}<br /><span className="mono">{data.squadron} · {String(data.base).toUpperCase()}</span></div>
          <div className="flex-1" />
          <div className="grid grid-cols-3 md:grid-cols-5 gap-x-6 gap-y-2">
            <Kv k="Airframe" v={`${fmt(data.hours_total)} FH`} />
            <Kv k="To minor" v={`${fmt(data.to_minor)} FH`} />
            <Kv k="To phase" v={`${fmt(data.to_phase)} FH`} />
            <Kv k="To overhaul" v={`${fmt(data.to_overhaul)} FH`} />
            <Kv k="P(snag 7 d)" v={<span style={{ color: data.p_snag_7d >= 0.4 ? "var(--warn)" : undefined }}>{fmtPct(data.p_snag_7d)}</span>} />
          </div>
        </div>
      </section>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-4">
        <Drawing data={data} />
        <div className="space-y-4 min-w-0">{data.engines.map((e: any, i: number) => <EnginePanel key={e.pos} e={e} idx={i + 1} n={data.engines.length} />)}</div>
      </div>
      <Panel title="Component record" meta="WEIBULL AFT · BASE ENVIRONMENT + MISSION SEVERITY" pad={false}>
        <div className="scroll-y max-h-[330px]">
          <table className="ledger">
            <thead><tr><th>LRU</th><th>ATA</th><th className="n">S/N</th><th className="n">Hrs since repair</th><th className="n">P(fail 7 d)</th><th className="n">P(fail 30 d)</th><th style={{ width: 120 }} /></tr></thead>
            <tbody>
              {[...data.lrus].sort((a: any, b: any) => b.p_fail_30d - a.p_fail_30d).map((l: any) => (
                <tr key={l.pos}>
                  <td>{l.name}</td><td className="m">{l.ata}</td>
                  <td className="n">{l.missing ? <Stamp tone="red" rotate={-2}>MISSING</Stamp> : l.serial}</td>
                  <td className="n">{fmt(l.hours_since_repair)}</td>
                  <td className="n">{fmtPct(l.p_fail_7d, 1)}</td>
                  <td className="n font-semibold" style={{ color: l.p_fail_30d >= 0.25 ? "var(--crit)" : l.p_fail_30d >= 0.1 ? "var(--warn)" : undefined }}>{fmtPct(l.p_fail_30d, 1)}</td>
                  <td className="align-middle"><Meter value={l.p_fail_30d} color={l.p_fail_30d >= 0.25 ? "var(--crit)" : l.p_fail_30d >= 0.1 ? "var(--warn)" : "var(--ink-3)"} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <TechLog data={data} />
    </div>
  );
}

/** Whiteprint planform with numbered balloons + parts list (borrowed from the logbook concept). */
function Drawing({ data }: { data: any }) {
  type Item = { x: number; y: number; name: string; sn: string; cond: string; hot: boolean };
  const items: Item[] = [];
  const ne = data.engines.length;
  data.engines.forEach((e: any, i: number) => {
    const [x, y] = ne === 1 ? [200, 470] : i === 0 ? [163, 470] : [237, 470];
    items.push({ x, y, name: ne === 1 ? "ENGINE" : `ENGINE ${i === 0 ? "(PORT)" : "(STBD)"}`, sn: String(e.serial), cond: `RUL ${fmt(e.rul_fh.med)} FH [${fmt(e.rul_fh.lo)}–${fmt(e.rul_fh.hi)}]`, hot: e.rul_fh.med < 40 });
  });
  [...data.lrus].filter((l: any) => l.ata !== 72).sort((a: any, b: any) => b.p_fail_30d - a.p_fail_30d).slice(0, 6 - ne).forEach((l: any) => {
    const [x, y] = ZONE_XY[l.ata] ?? [200, 300];
    items.push({ x, y, name: l.name.toUpperCase(), sn: l.missing ? "MISSING" : String(l.serial), cond: `P(FAIL 30 D) ${fmtPct(l.p_fail_30d)}`, hot: l.missing || l.p_fail_30d >= 0.25 });
  });
  const S = 0.6, TX = 100, TY = 8;
  const pts = items.map((it, i) => ({ i, px: TX + S * it.x, py: TY + S * it.y }));
  const balloons: Balloon[] = [];
  for (const side of ["L", "R"] as const) {
    let prev = -100;
    pts.filter((p) => (side === "R" ? p.px >= 220 : p.px < 220)).sort((a, b) => a.py - b.py).forEach((p) => {
      const by = Math.max(p.py - 10, prev + 32, 20);
      prev = by;
      const it = items[p.i];
      balloons.push({ n: p.i + 1, x: it.x, y: it.y, bx: side === "R" ? 405 : 35, by: Math.min(by, 315), hot: it.hot, title: `${it.name} · ${it.cond}` });
    });
  }
  const eng = data.engines.find((e: any) => e.rul_fh.med < 40);
  return (
    <section className="panel">
      <div className="lp"><span>Condition drawing</span><span className="meta">DWG TPR-AF-{data.tail.slice(3)}</span></div>
      <div className="whiteprint px-3 pt-2 pb-3">
        <Planform balloons={balloons} highlight={eng ? { x: ne === 1 ? 200 : data.engines.indexOf(eng) === 0 ? 163 : 237, y: 470 } : undefined} />
        <table className="parts mt-1">
          <thead><tr><th>ITEM</th><th>COMPONENT</th><th>S/N</th><th>CONDITION (MODEL)</th></tr></thead>
          <tbody>{items.map((it, i) => (
            <tr key={i} style={{ color: it.hot ? "var(--stamp-red)" : undefined }}><td>{i + 1}</td><td className="cond font-semibold text-[12.5px]">{it.name}</td><td>{it.sn}</td><td>{it.cond}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

function EnginePanel({ e, idx, n }: { e: any; idx: number; n: number }) {
  const { tokens: t } = useTheme();
  const xs = e.trend.map((p: any) => p.cycle);
  const hot = e.rul_fh.med < 40;
  const opt = {
    grid: grid({ top: 12, right: 14, left: 40, bottom: 34 }),
    tooltip: tooltip(t, { formatter: (ps: any[]) => { const p = e.trend[ps[0].dataIndex]; return `CYCLE <b>${p.cycle}</b><br/>RUL <b>${p.med.toFixed(0)}</b> CYCLES (${p.lo.toFixed(0)}–${p.hi.toFixed(0)})`; } }),
    xAxis: { type: "category", data: xs, boundaryGap: false, name: "HUMS CYCLE", nameLocation: "middle", nameGap: 22, nameTextStyle: { color: t["ink-3"], fontFamily: "IBM Plex Mono", fontSize: 10 }, axisLabel: { color: t["ink-3"], fontSize: 10, fontFamily: "IBM Plex Mono" }, axisLine: { lineStyle: { color: t.ink } }, axisTick: { show: false }, splitLine: { show: true, lineStyle: { color: t.grid } } },
    yAxis: yVal(t, { name: "RUL CYC", nameTextStyle: { color: t["ink-3"], fontFamily: "IBM Plex Mono", fontSize: 10, align: "left" } }),
    series: [
      { type: "line", data: e.trend.map((p: any) => p.lo), stack: "b", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true, tooltip: { show: false } },
      { type: "line", data: e.trend.map((p: any) => p.hi - p.lo), stack: "b", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: t.tat, opacity: 0.16 }, silent: true },
      { name: "Median RUL", type: "line", data: e.trend.map((p: any) => p.med), symbol: "none", lineStyle: { color: hot ? t.crit : t.tat, width: 2 } },
    ],
  };
  const mods = Object.entries(e.modules as Record<string, number>).filter(([k]) => k !== "Usage / age").sort((a, b) => a[1] - b[1]);
  const max = Math.max(1, ...mods.map(([, v]) => Math.abs(v)));
  return (
    <Panel title={`Engine ${n > 1 ? idx : ""} · S/N ${e.serial}`} meta={`HUMS ${e.hums_source} · CYCLE ${e.cycle}`}>
      <div className="flex flex-wrap items-baseline gap-x-3 mb-1">
        <span className="cond text-[13px] ink-3">REMAINING LIFE</span>
        <span className="mono font-bold text-[22px]" style={{ color: hot ? "var(--crit)" : undefined }}>{fmt(e.rul_fh.med)} FH</span>
        <span className="mono text-[12px] ink-2">90 % CONFORMAL {fmt(e.rul_fh.lo)}–{fmt(e.rul_fh.hi)} FH</span>
        {hot && <Stamp tone="red" rotate={-3}>CHANGE AT PHASE</Stamp>}
        {e.uploaded && <Stamp tone="blue" rotate={2}>UPDATED FROM HUMS DOWNLOAD</Stamp>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-3">
        <Chart option={opt} height={170} />
        <div>
          <div className="cond text-[12px] ink-3 mb-1">WHERE IS THE DEGRADATION (SHAP, CYCLES OF LIFE)</div>
          {mods.map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 mono text-[11px] mb-[3px]">
              <span className="w-[96px] truncate">{k.toUpperCase()}</span>
              <span className="flex-1 h-[7px]" style={{ background: "var(--rule-2)" }}><span className="block h-[7px]" style={{ width: `${(Math.abs(v) / max) * 100}%`, background: v < 0 ? "var(--crit)" : "var(--tat)" }} /></span>
              <span className="w-[42px] text-right">{v.toFixed(1)}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

/** Recent snags as Form-700 entries (borrowed from the logbook concept). */
function TechLog({ data }: { data: any }) {
  return (
    <div className="f700">
      <div className="fh"><h3>Technical log — {data.tail}</h3><span>FORM 700 (NOTIONAL) · MOST RECENT FIRST</span></div>
      {data.chronic.length > 0 && <div className="mono text-[12px] mb-2"><span className="redpen">CHRONIC DEFECT: ATA {data.chronic.map((c: any) => c.ata).join(", ")} — REPEATED SNAGS WITHIN 30 DAYS</span></div>}
      <div className="scroll-y max-h-[460px]"><table>
        <thead><tr><th style={{ width: 92 }}>Date</th><th style={{ width: 44 }}>ATA</th><th>Defect reported</th><th>Rectification</th><th style={{ width: 128 }}>Finding</th></tr></thead>
        <tbody>{data.snags.map((s: any) => (
          <tr key={s.snag_id}>
            <td className="n">{s.date.slice(0, 10)}</td><td>{s.ata}</td><td>{s.text}</td><td>{s.action}</td>
            <td><Stamp tone={s.finding === "NFF" ? "grey" : "red"} rotate={(s.snag_id.charCodeAt(s.snag_id.length - 1) % 5) - 2}>{s.finding === "NFF" ? "NFF" : s.finding}</Stamp></td>
          </tr>
        ))}</tbody>
      </table></div>
    </div>
  );
}
