import { useState, type ReactNode } from "react";
import { Stamp } from "../components/glyphs";
import { Chart } from "../components/Chart";
import { Board, ErrorBox, Loading, Meter, Panel } from "../components/ui";
import { download, fmt, fmtPct, getJSON, postForm, postJSON, useApi, useIngestStamp } from "../lib/api";
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
  const seq = useIngestStamp(6000);
  const src = useApi<any>("/api/data/sources", [seq]);
  const mdl = useApi<any>("/api/models");
  const audit = useApi<any>("/api/audit", [seq]);
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
      <Panel title="Provenance — sources" meta={`QUALITY = COMPLETENESS · CONSISTENCY · FRESHNESS · REF ${data.today}`} pad={false}>
        <div className="scroll-y">
          <table className="ledger">
            <thead><tr><th>Source</th><th>Entity</th><th>S5000F</th><th>OSA-CBM</th><th className="n">Rows</th><th className="n">Fresh</th><th>Unit import</th><th style={{ width: 140 }}>Quality</th></tr></thead>
            <tbody>{data.sources.map((s: any) => (
              <tr key={s.key}><td className="font-semibold">{s.label}</td><td className="ink-2">{s.entity}</td><td className="ink-2">{s.s5000f}</td><td className="m">{s.osa_cbm}</td>
                <td className="n">{fmt(s.rows)}</td><td className="n">{s.freshness_days != null ? `${s.freshness_days} D` : "—"}</td>
                <td className="m text-[11px]">{s.last_import ? <b>{String(s.last_import.ts).slice(5, 16).replace("T", " ")}Z · {s.last_import.accepted} ROWS</b> : s.ingest ? <span className="ink-3">CSV · {String(s.ingest).toUpperCase()}</span> : <span className="ink-3">—</span>}</td>
                <td><div className="flex items-center gap-2"><Meter value={s.score} color={s.score >= 0.9 ? "var(--good)" : "var(--warn)"} /><span className="mono text-[11.5px]">{fmtPct(s.score)}</span></div></td></tr>))}
            </tbody>
          </table>
        </div>
      </Panel>
      <DataFabric seq={seq}>
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
        </Panel>
      </DataFabric>

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
        <Panel title="Federated learning across bases" meta={`FEDAVG · ${fl.rounds} ROUNDS · ONLY WEIGHTS + AGGREGATE STATISTICS LEAVE A BASE`} pad={false} className="mt-4">
          <table className="ledger"><thead><tr><th>Training regime</th>{Object.keys(fl.clients).map((b) => <th key={b} className="n">{b} <span className="ink-3">{fl.clients[b]}</span></th>)}<th className="n">Mean RMSE</th><th>Raw data leaves base?</th></tr></thead>
            <tbody>{fl.results.map((r: any) => <tr key={r.regime}><td>{r.regime}</td>
              {Object.keys(fl.clients).map((b) => <td key={b} className="n">{fmt(r.per_base[b], 1)}</td>)}
              <td className="n font-bold">{fmt(r.rmse, 2)}</td><td className="m">{String(r.data_moved).toUpperCase()}</td></tr>)}</tbody></table>
          <div className="foot px-3 pb-2">RMSE in cycles on each base's held-out NASA test engines. Leh (8 engines of history) gains most: {fmt(fl.results[0].per_base.Leh, 1)} → {fmt(fl.results[1].per_base.Leh, 1)} without sharing a single engine record. Each base is scored on its own test engines; the local-only baseline gets the same training steps.</div>
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

const SOURCE_LABEL: Record<string, string> = { hums: "HUMS", snags: "TECH LOG", stock: "STOCK · IMMOLS", repairs: "REPAIRS · BRD/HAL", sorties: "SORTIES" };

/** Data fabric: a unit imports its own exports. Contract → validate → import → what changed, all on the record. */
function DataFabric({ seq, children }: { seq: number; children?: ReactNode }) {
  const { can } = useAuth();
  const contracts = useApi<any[]>("/api/ingest/contracts");
  const lineage = useApi<any[]>("/api/ingest/lineage", [seq]);
  const [src, setSrc] = useState("hums");
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<any>(null);
  const [done, setDone] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showFields, setShowFields] = useState(false);
  if (contracts.error) return <ErrorBox error={contracts.error} />;
  if (!contracts.data) return null;
  const c = contracts.data.find((x) => x.source === src)!;
  const pick = (s: string) => { setSrc(s); setFile(null); setCheck(null); setDone(null); setErr(null); setShowFields(false); };
  const form = (f: File) => { const fd = new FormData(); fd.append("file", f); return fd; };
  const validate = async (f: File) => {
    setFile(f); setDone(null); setErr(null); setBusy(true);
    try { setCheck((await postForm(`/api/ingest/${src}/validate`, form(f))).report); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const doImport = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try { setDone(await postForm(`/api/ingest/${src}`, form(file))); lineage.setData(await getJSON("/api/ingest/lineage")); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const reset = async () => {
    if (!window.confirm("Remove every imported file and return to the generated fleet state?")) return;
    setBusy(true);
    try { await postJSON("/api/ingest/reset", {}); setDone(null); setCheck(null); lineage.setData(await getJSON("/api/ingest/lineage")); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const perm = `data:import:${src}`;
  const res = done?.result;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-4 mt-4">
      <Panel title="Data fabric — import unit data" meta="CONTRACT → VALIDATE → IMPORT → LEDGER">
        <div className="flex flex-wrap gap-1.5 mb-3" role="tablist" aria-label="Data source">
          {contracts.data.map((x) => (
            <button key={x.source} role="tab" aria-selected={x.source === src} className={`btn ${x.source === src ? "on" : ""}`} onClick={() => pick(x.source)}>{SOURCE_LABEL[x.source] ?? x.source}</button>
          ))}
        </div>
        <div className="text-[13px] leading-snug mb-2"><b>{c.title}.</b> <span className="ink-2">{c.system}.</span></div>
        <div className="text-[13px] leading-snug mb-2"><span className="cond ink-3 text-[12px]">AN IMPORT </span>{c.applies}</div>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button className="btn" onClick={() => download(`/api/ingest/template/${src}`, `tatpar_${src}_template.csv`).catch((e) => setErr(String(e)))}>TEMPLATE CSV</button>
          <button className="btn" onClick={() => download(`/api/ingest/template/${src}?sample=true`, `tatpar_${src}_sample.csv`).catch((e) => setErr(String(e)))}>SAMPLE CSV</button>
          <label className="btn ink">CHOOSE CSV<input type="file" accept=".csv,text/csv" className="hidden" aria-label="Choose CSV" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) validate(f); }} /></label>
          <button className="btn" onClick={() => setShowFields(!showFields)}>{showFields ? "HIDE" : "SHOW"} CONTRACT · {c.fields.length} FIELDS</button>
        </div>
        {showFields && (
          <div className="scroll-y max-h-[240px] mb-2"><table className="ledger"><thead><tr><th>Field</th><th>Type</th><th>Unit</th><th>Req.</th><th>Allowed</th><th>Meaning</th></tr></thead>
            <tbody>{c.fields.map((f: any) => <tr key={f.name}><td className="m">{f.name}</td><td className="m">{f.type}</td><td className="m">{f.unit}</td><td className="m">{f.required ? "YES" : ""}</td>
              <td className="m text-[11px]">{f.values.length ? f.values.join(" · ") : f.lo != null ? `${f.lo} – ${f.hi}` : ""}</td><td className="text-[12px] ink-2">{f.doc}</td></tr>)}</tbody></table></div>
        )}
        {busy && <Loading label={done ? "IMPORTING" : "VALIDATING"} />}
        {err && <div className="mono text-[12px]" style={{ color: "var(--crit)" }}>{err}</div>}
        {check && !busy && (
          <div className="mono text-[12px] space-y-1 mt-2" aria-live="polite">
            <div className="flex flex-wrap items-center gap-3">
              <Stamp tone={check.ok ? "green" : "red"} rotate={-2}>{check.ok ? (check.rejected ? "PARTLY ACCEPTED" : "ACCEPTED") : "REJECTED"}</Stamp>
              <span>{file?.name} · {fmt(check.rows)} ROWS · {fmt(check.accepted)} OK · {fmt(check.rejected)} REJECTED{check.completeness != null ? ` · COMPLETENESS ${fmtPct(check.completeness, 1)}` : ""}</span>
            </div>
            {check.errors?.map((e: string) => <div key={e} style={{ color: "var(--crit)" }}>✕ {e}</div>)}
            {check.row_errors?.slice(0, 8).map((r: any) => <div key={r.line} style={{ color: "var(--crit)" }}>✕ LINE {r.line}: {r.reasons.join("; ")}</div>)}
            {check.warnings?.map((w: string) => <div key={w} style={{ color: "var(--warn)" }}>! {w}</div>)}
            {check.engines && <div className="ink-2">ENGINES: {check.engines.map((e: any) => `${e.tail} E${e.engine} (${e.cycles} CYCLES)`).join(" · ")}</div>}
            {check.ok && !done && (c.validate_only ? <div className="ink-3">{c.applies}</div>
              : can(perm) ? <button className="btn ink mt-1" onClick={doImport}>IMPORT {fmt(check.accepted)} ROWS AS {String(SOURCE_LABEL[src])}</button>
              : <div className="ink-3">IMPORTING {String(SOURCE_LABEL[src])} NEEDS A DIFFERENT AUTHORITY (THE SERVER CHECKS THE ROLE).</div>)}
          </div>
        )}
        {done && !busy && (
          <div className="mono text-[12px] space-y-1 mt-2" aria-live="polite">
            <div className="flex flex-wrap items-center gap-3">
              <Stamp tone={done.applied ? "green" : "red"} rotate={-3}>{done.applied ? `IMPORTED · #${done.lineage.seq}` : "NOT IMPORTED"}</Stamp>
              <span>{res?.summary}</span>
            </div>
            {res?.engines?.map((e: any) => (
              <div key={e.serial}>{e.tail} ENGINE {e.engine} (S/N {e.serial}, {e.cycles} CYCLES): RUL {fmt(e.before_fh.med)} → <b>{fmt(e.after_fh.med)} FH</b> (90 % {fmt(e.after_fh.lo)}–{fmt(e.after_fh.hi)}){e.alert && <b style={{ color: "var(--crit)" }}> · ALERT</b>} · <a href={`/aircraft/${e.tail}`}>OPEN {e.tail} →</a></div>
            ))}
            {res?.repeats?.map((r: string) => <div key={r} style={{ color: "var(--warn)" }}>! {r}</div>)}
            {res?.rows?.slice(0, 6).map((r: any, i: number) => <div key={i} className="ink-2">{r.stock_point ? `${String(r.stock_point).toUpperCase()} ${r.lru}: ${r.before} → ${r.after}` : `S/N ${r.serial} ${r.lru} ${r.status}: RETURN ${r.before} → ${r.after}${r.condemned ? " · CONDEMNED" : ""}`}</div>)}
            {done.applied && <div className="ink-3">RECORDED IN THE DECISION LEDGER WITH THE FILE'S SHA-256. RISK, ALERTS, FORECASTS AND THE PLANNER NOW USE THIS DATA.</div>}
          </div>
        )}
      </Panel>
      <div className="space-y-4 min-w-0">
      <Panel title="Import register" meta="EVERY FILE · WHO · HASH" pad={false}>
        {!lineage.data?.length ? <div className="pad mono text-[12px] ink-3">NO UNIT DATA IMPORTED. THE BOARDS SHOW THE GENERATED NOTIONAL FLEET.</div> : (
          <div className="scroll-y max-h-[340px] overflow-x-auto"><table className="ledger"><thead><tr><th className="n">#</th><th>Time (UTC)</th><th>Source</th><th>File</th><th className="n">OK / rej.</th><th>By</th><th>SHA-256</th></tr></thead>
            <tbody>{lineage.data.map((e: any) => <tr key={e.seq}><td className="n">{e.seq}</td><td className="m">{String(e.ts).slice(5, 16).replace("T", " ")}</td><td className="m">{String(SOURCE_LABEL[e.source] ?? e.source).split(" · ")[0]}</td>
              <td className="m text-[11px] truncate max-w-[110px]" title={e.file}>{e.file}</td><td className="n">{e.accepted} / {e.rejected}</td><td className="m">{e.role}</td><td className="m text-[11px]">{String(e.sha256).slice(0, 10)}…</td></tr>)}</tbody></table></div>
        )}
        {can("data:reset") && !!lineage.data?.length && <div className="pad pt-2"><button className="btn" onClick={reset} disabled={busy}>REMOVE ALL IMPORTS</button></div>}
        <div className="foot px-3 pb-2">Edge gateway for live HUMS: <span className="mono">python -m tatpar.ingest.gateway</span> replays post-flight downloads into this server.</div>
      </Panel>
      {children}
      </div>
    </div>
  );
}
