import { useState } from "react";
import { Stamp } from "../components/glyphs";
import { Chart } from "../components/Chart";
import { Board, ErrorBox, Loading, Meter, Panel } from "../components/ui";
import { fmt, fmtPct, postForm, useApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { grid, MONO, tooltip, yVal } from "../lib/charts";
import { SQN_COLOR, useTheme } from "../lib/theme";

const LAYERS: string[][] = [
  ["HUMS", "Tech log", "Flying records", "Spares ERP", "Repair agencies"],
  ["Common data model · S5000F / ATA iSpec 2200 / OSA-CBM"],
  ["Engine RUL", "LRU survival", "NFF / rogue", "Snag NLP"],
  ["Fleet Twin"],
  ["Flight & maint plan", "Sparing", "Planning cell"],
  ["Ops room boards 01–07"],
];

/** 08 PROOF: where every number comes from, how good the models are, and the decision ledger. */
export default function ProofPage() {
  const { tokens: t } = useTheme();
  const src = useApi<any>("/api/data/sources");
  const mdl = useApi<any>("/api/models");
  const audit = useApi<any>("/api/audit");
  if (src.error || mdl.error) return <ErrorBox error={(src.error || mdl.error)!} />;
  if (!src.data || !mdl.data) return <Loading />;
  const data = src.data, m = mdl.data;
  const rul = m.cards.find((c: any) => c.id === "engine_rul").metrics;
  const subsets = ["FD001", "FD002", "FD003", "FD004", "ALL"];
  const covOpt = {
    grid: grid({ top: 26, left: 40, bottom: 24, right: 10 }),
    legend: { top: 0, left: 0, icon: "rect", itemWidth: 12, itemHeight: 8, textStyle: { color: t["ink-2"], fontFamily: MONO, fontSize: 10.5 }, data: ["RAW QUANTILE MODEL", "CONFORMAL (CALIBRATED)"] },
    tooltip: tooltip(t, { valueFormatter: (v: number) => fmtPct(v, 1) }),
    xAxis: { type: "category", data: subsets, axisLabel: { color: t["ink-2"], fontFamily: MONO, fontSize: 10.5 }, axisLine: { lineStyle: { color: t.ink } }, axisTick: { show: false } },
    yAxis: yVal(t, { min: 0.6, max: 1, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5, formatter: (v: number) => `${Math.round(v * 100)}%` } }),
    series: [
      { name: "RAW QUANTILE MODEL", type: "bar", barMaxWidth: 20, data: subsets.map((s) => rul[s].picp90_uncalibrated), itemStyle: { color: t.cur } },
      { name: "CONFORMAL (CALIBRATED)", type: "bar", barMaxWidth: 20, data: subsets.map((s) => rul[s].picp90), itemStyle: { color: t.tat },
        markLine: { symbol: "none", data: [{ yAxis: 0.9 }], lineStyle: { color: t.crit, type: "solid", width: 1.5 }, label: { color: t.crit, fontFamily: MONO, fontWeight: 700, position: "insideEndTop", formatter: "TARGET 90 %" } } },
    ],
  };
  const pts = m.calibration_points;
  const bases = ["jodhpur", "pune", "tezpur", "thanjavur"];
  const lifeOpt = {
    grid: grid({ top: 30, left: 50, bottom: 40, right: 26 }),
    legend: { top: 0, left: 0, icon: "rect", itemWidth: 10, itemHeight: 10, textStyle: { color: t["ink-2"], fontFamily: MONO, fontSize: 10.5 }, data: bases.map((b) => b.toUpperCase()) },
    tooltip: { trigger: "item", backgroundColor: t.panel, borderColor: t.ink, borderRadius: 0, textStyle: { color: t.ink, fontSize: 12, fontFamily: MONO },
      formatter: (p: any) => `<b>${p.data[2]}</b> @ ${p.seriesName}<br/>PREDICTED ${fmt(p.data[0])} FH · TRUE ${fmt(p.data[1])} FH` },
    xAxis: { type: "log", name: "PREDICTED MEAN LIFE (FH)", nameLocation: "middle", nameGap: 24, min: 150, max: 6000, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5 }, splitLine: { lineStyle: { color: t.grid } }, axisLine: { lineStyle: { color: t.ink } }, nameTextStyle: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5 } },
    yAxis: { type: "log", min: 150, max: 6000, axisLabel: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5 }, splitLine: { lineStyle: { color: t.grid } }, nameTextStyle: { color: t["ink-3"], fontFamily: MONO, fontSize: 10.5 } },
    series: [
      ...bases.map((b, i) => ({
        name: b.toUpperCase(), type: "scatter", symbol: ["circle", "rect", "triangle", "diamond"][i], symbolSize: 8,
        data: pts.filter((p: any) => p.base === b).map((p: any) => [p.pred, p.true, p.lru]),
        itemStyle: { color: SQN_COLOR(t, i), borderColor: t.panel, borderWidth: 1 },
      })),
      { type: "line", data: [[150, 150], [6000, 6000]], symbol: "none", lineStyle: { color: t["ink-3"], width: 1, type: [4, 3] }, silent: true, tooltip: { show: false } },
    ],
  };
  const fl = m.federated;
  return (
    <Board no="08" title="Proof" sub="Where every number on every board comes from, how good the models are (on data they never saw), and the tamper-evident ledger of every decision taken in this room.">
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-4">
        <Panel title="Provenance — sources" meta={`QUALITY = COMPLETENESS · CONSISTENCY · FRESHNESS · REF ${data.today}`} pad={false}>
          <div className="scroll-y">
            <table className="ledger">
              <thead><tr><th>Source</th><th>Entity</th><th>S5000F</th><th>OSA-CBM</th><th className="n">Rows</th><th className="n">Fresh</th><th style={{ width: 140 }}>Quality</th></tr></thead>
              <tbody>{data.sources.map((s: any) => (
                <tr key={s.key}><td className="font-semibold">{s.label}</td><td className="ink-2">{s.entity}</td><td className="ink-2">{s.s5000f}</td><td className="m">{s.osa_cbm}</td>
                  <td className="n">{fmt(s.rows)}</td><td className="n">{s.freshness_days != null ? `${s.freshness_days} D` : "—"}</td>
                  <td><div className="flex items-center gap-2"><Meter value={s.score} color={s.score >= 0.9 ? "var(--good)" : "var(--warn)"} /><span className="mono text-[11.5px]">{fmtPct(s.score)}</span></div></td></tr>))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="Lineage" meta="EVERY NUMBER TRACES DOWN THIS CHAIN">
          <div className="flex flex-col items-center gap-1">
            {LAYERS.map((row, i) => (
              <div key={i} className="flex flex-col items-center">
                <div className="flex flex-wrap justify-center gap-1.5">
                  {row.map((n) => <span key={n} className="tag" style={i === 3 ? { borderColor: "var(--accent)", color: "var(--ink)", borderWidth: 2 } : undefined}>{n.toUpperCase()}</span>)}
                </div>
                {i < LAYERS.length - 1 && <div className="mono ink-3 text-[12px] leading-none py-0.5">↓</div>}
              </div>
            ))}
          </div>
          <Validate />
        </Panel>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
        <Panel title="Engine RUL — 90 % interval coverage" meta="NASA C-MAPSS OFFICIAL TEST SETS">
          <Chart option={covOpt} height={250} />
          <div className="foot">A 90 % interval should contain the true remaining life 90 % of the time. Conformal calibration fixes the raw model's over-confidence on every subset.</div>
        </Panel>
        <Panel title="Reliability models recover the hidden truth" meta="PER LRU TYPE AND BASE · LOG SCALE">
          <Chart option={lifeOpt} height={250} />
          <div className="foot">Y axis: true mean life (FH) from the twin's hidden truth. X axis: Weibull AFT prediction fitted on recorded removals only. Dashed diagonal = perfect.</div>
        </Panel>
      </div>

      {fl && (
        <Panel title="Federated learning across bases" meta={`FEDAVG · ${fl.rounds} ROUNDS · ONLY WEIGHTS LEAVE A BASE`} pad={false} className="mt-4">
          <table className="ledger"><thead><tr><th>Training regime</th>{Object.keys(fl.clients).map((b) => <th key={b} className="n">{b} <span className="ink-3">{fl.clients[b]}</span></th>)}<th className="n">Mean RMSE</th><th>Raw data leaves base?</th></tr></thead>
            <tbody>{fl.results.map((r: any) => <tr key={r.regime}><td>{r.regime}</td>
              {Object.keys(fl.clients).map((b) => <td key={b} className="n">{fmt(r.per_base[b], 1)}</td>)}
              <td className="n font-bold">{fmt(r.rmse, 2)}</td><td className="m">{String(r.data_moved).toUpperCase()}</td></tr>)}</tbody></table>
          <div className="foot px-3 pb-2">RMSE in cycles on each base's held-out NASA test engines. Leh (8 engines of history) gains most: {fmt(fl.results[0].per_base.Leh, 1)} → {fmt(fl.results[1].per_base.Leh, 1)} without sharing a single sensor record.</div>
        </Panel>
      )}

      <div className="mt-4">
        <div className="cond font-semibold text-[15px] mb-2 tracking-[.12em]">Model data plates</div>
        <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3">
          {m.cards.map((c: any) => <DataPlate key={c.id} c={c} />)}
        </div>
      </div>

      <section className="panel mt-4">
        <div className="lp"><span>Decision ledger</span><span className="meta">APPEND-ONLY · SHA-256 HASH CHAIN</span></div>
        <div className="pad">
          {audit.data && (
            <div className="flex flex-wrap items-center gap-4 mb-3">
              <Stamp tone={audit.data.verify.ok ? "green" : "red"} rotate={-3}>{audit.data.verify.ok ? "CHAIN VERIFIED" : `BROKEN AT #${audit.data.verify.broken_at}`}</Stamp>
              <span className="mono text-[11.5px] ink-2">{audit.data.verify.entries} ENTRIES · HEAD {String(audit.data.verify.head ?? "").slice(0, 16)}…</span>
            </div>
          )}
          {!audit.data?.entries?.length ? <div className="mono text-[12px] ink-3">NO DECISIONS YET. RELEASE THE SIGNAL ON 01 STATE OR APPROVE AN ORDER IN 02 PLANNING CELL.</div> : (
            <div className="scroll-y max-h-[380px]">
              <table className="ledger"><thead><tr><th className="n">#</th><th>Time (UTC)</th><th>Authority</th><th>Kind</th><th>Summary</th><th>Prev → hash</th></tr></thead>
                <tbody>{[...audit.data.entries].reverse().map((e: any) => (
                  <tr key={e.seq}><td className="n">{e.seq}</td><td className="m">{String(e.ts).replace("T", " ").replace("+00:00", "Z")}</td><td className="m">{e.persona}</td><td className="m">{String(e.kind).toUpperCase()}</td><td>{e.summary}</td>
                    <td className="m text-[11px]"><span className="ink-3">{String(e.prev).slice(0, 8)}</span> → <b>{e.hash.slice(0, 8)}</b></td></tr>))}</tbody></table>
            </div>
          )}
          <div className="foot">Each entry stores SHA-256(previous hash + entry). Editing any earlier record breaks every hash after it. In service the head would be countersigned with the unit's PKI key.</div>
        </div>
      </section>
    </Board>
  );
}

/** Model card as an equipment data plate: what it is for, what it was trained on, how it scored. */
function DataPlate({ c }: { c: any }) {
  const flat: [string, number][] = [];
  const walk = (o: any, p = "") => Object.entries(o || {}).forEach(([k, v]) => {
    if (k === "per_lru") return;
    if (v && typeof v === "object" && !Array.isArray(v)) walk(v, `${p}${k} · `);
    else if (typeof v === "number") flat.push([`${p}${k}`, v]);
  });
  walk(c.metrics);
  return (
    <div className="panel" style={{ borderColor: "var(--ink-3)" }}>
      <div className="lp"><span>{c.name}</span></div>
      <div className="pad text-[12px] space-y-1.5">
        <div><span className="cond ink-3 mr-1">USE</span>{c.intended_use}</div>
        <div><span className="cond ink-3 mr-1">DATA</span>{c.data}</div>
        <div><span className="cond ink-3 mr-1">LIMITS</span>{c.limits}</div>
        <div className="grid grid-cols-2 gap-x-3 pt-1 border-t" style={{ borderColor: "var(--rule-2)" }}>
          {flat.slice(0, 10).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2 mono text-[10.5px] border-b border-dotted" style={{ borderColor: "var(--rule)" }}>
              <span className="ink-3 truncate">{k.replaceAll("_", " ").toUpperCase()}</span>
              <span className="font-semibold">{Number.isInteger(v) ? fmt(v) : Math.abs(v) <= 1 ? v.toFixed(3) : fmt(v, 1)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Validate() {
  const { can } = useAuth();
  const [kind, setKind] = useState("snags");
  const [report, setReport] = useState<any>(null);
  const [file, setFile] = useState<File | null>(null);
  const [imported, setImported] = useState<any>(null);
  const upload = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    setFile(f);
    setImported(null);
    setReport(await postForm(`/api/data/validate?kind=${kind}`, fd).catch((e) => ({ ok: false, rows: 0, errors: [String(e)] })));
  };
  const doImport = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setImported(await postForm("/api/snags/import", fd).catch((e) => ({ filed: 0, errors: [String(e)] })));
  };
  return (
    <div className="mt-4 pt-3 border-t" style={{ borderColor: "var(--rule)" }}>
      <div className="cond text-[13px] font-semibold mb-1">Validate an export · import snags into the tech log</div>
      <div className="flex flex-wrap items-center gap-2">
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Export kind">
          <option value="snags">SNAGS (date, tail, text)</option><option value="stock">STOCK (stock_point, lru, qty)</option><option value="sorties">SORTIES (date, tail, hours)</option>
        </select>
        <label className="btn">CHOOSE CSV<input type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>
      </div>
      {report && (
        <div className="mt-2 mono text-[12px] space-y-1">
          <div><b style={{ color: report.ok ? "var(--good)" : "var(--crit)" }}>{report.ok ? "ACCEPTED" : "REJECTED"}</b> · {fmt(report.rows)} ROWS · COMPLETENESS {fmtPct(report.completeness, 1)}</div>
          {report.errors?.map((e: string) => <div key={e} style={{ color: "var(--crit)" }}>✕ {e}</div>)}
          {report.warnings?.map((w: string) => <div key={w} style={{ color: "var(--warn)" }}>! {w}</div>)}
          {report.ata_preview?.slice(0, 5).map((p: any, i: number) => <div key={i} className="ink-2">{p.text} → ATA {p.ata.ata} ({fmtPct(p.ata.p)})</div>)}
          {report.ok && kind === "snags" && !imported && (can("data:import")
            ? <button className="btn ink mt-1" onClick={doImport}>IMPORT {report.rows} ENTRIES INTO THE TECH LOG</button>
            : <div className="ink-3">IMPORT NEEDS STN CDR / SENGO / LOG OFFR.</div>)}
          {imported && <div style={{ color: imported.filed ? "var(--good)" : "var(--crit)" }}>
            {imported.filed ? `FILED ${imported.filed} ENTRIES (${imported.first} … ${imported.last}) — SEE 07 TECH LOG` : `NOTHING FILED ${imported.errors?.join("; ") ?? ""}`}</div>}
        </div>
      )}
    </div>
  );
}
