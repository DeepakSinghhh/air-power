import { Search } from "lucide-react";
import { useState } from "react";
import { Card, Chart, ErrorBox, Loading, PageHeader } from "../components/ui";
import { fmtPct, postJSON, useApi } from "../lib/api";
import { grid, tooltip, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

const EXAMPLES = [
  "HYD PR FLUCTUATING ON LH SYS DURING TAXI",
  "HYD PRESSURE LH SYSTEM MEIN FLUCTUATION, TAXI KE DAURAN",
  "FCS CHANNEL 2 FAIL DURING TAKE OFF. FAULT CLEARED ON BITE RESET",
  "Radar TX fail in A2A mode, intermittent",
  "LEFT MAG DROP EXCESSIVE ON RUNUP",
  "No 1 eng EGT margin low, thrust low on take off",
];

export default function SnagsPage() {
  const { tokens: t } = useTheme();
  const [text, setText] = useState(EXAMPLES[0]);
  const [tail, setTail] = useState("HF-101");
  const [lru, setLru] = useState("");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const meta = useApi<any>("/api/meta");
  const stats = useApi<any>("/api/snags/stats");
  const recent = useApi<any[]>("/api/snags/recent");
  const fleet = useApi<any[]>("/api/fleet");
  const analyse = async (txt = text) => {
    setBusy(true);
    try {
      setRes(await postJSON("/api/snags/analyse", { text: txt, tail, lru: lru || null }));
    } finally {
      setBusy(false);
    }
  };
  if (stats.error) return <ErrorBox error={stats.error} />;
  const by = stats.data?.by_ata ?? [];
  const paretoOpt = {
    grid: grid({ left: 170, top: 8, right: 50, bottom: 24 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => `<b>${p.value}</b> snags · ${by[p.dataIndex].nff} NFF<br/>ATA ${by[p.dataIndex].ata} ${by[p.dataIndex].system}` }),
    xAxis: yVal(t),
    yAxis: { type: "category", inverse: true, data: by.map((r: any) => `ATA ${r.ata} ${r.system}`), axisLabel: { color: t["text-secondary"], fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar", barWidth: 12, data: by.map((r: any) => ({ value: r.snags, itemStyle: { color: t["series-1"], borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: t["text-secondary"], fontSize: 11 } }],
  };
  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Snag intelligence" sub="Type a technical-log entry the way it is written — abbreviations and Hinglish welcome. TATPAR codes it to an ATA chapter, finds similar past cases (fleet + real MaintNet logbooks), ranks fixes by repeat-defect rate, and flags likely No-Fault-Found removals." />
      <Card title="Analyse a snag">
        <div className="flex flex-col gap-3">
          <textarea className="input min-h-[70px] font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex flex-wrap gap-2 items-center">
            <select className="input" value={tail} onChange={(e) => setTail(e.target.value)}>{(fleet.data || []).map((f) => <option key={f.tail}>{f.tail}</option>)}</select>
            <select className="input" value={lru} onChange={(e) => setLru(e.target.value)}>
              <option value="">Suspect LRU (optional)</option>
              {(meta.data?.lrus || []).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            <button className="btn btn-primary" onClick={() => analyse()} disabled={busy}><Search size={14} />{busy ? "Analysing…" : "Analyse"}</button>
            <span className="muted text-[12px]">Examples:</span>
            {EXAMPLES.slice(1).map((e) => <button key={e} className="chip" onClick={() => { setText(e); analyse(e); }}>{e.length > 34 ? e.slice(0, 34) + "…" : e}</button>)}
          </div>
        </div>
      </Card>
      {res && (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_2fr] gap-4">
          <div className="space-y-4">
            <Card title="ATA chapter">
              {res.ata.map((a: any, i: number) => (
                <div key={a.ata} className="flex items-center gap-3 py-1">
                  <span className={`tabular ${i === 0 ? "text-[20px] font-bold" : "text-[14px]"}`}>ATA {a.ata}</span>
                  <span className="flex-1 secondary">{a.name}</span>
                  <span className="tabular font-semibold">{fmtPct(a.p)}</span>
                </div>
              ))}
            </Card>
            <Card title="Removal decision">
              {res.nff ? (
                <div>
                  <div className="text-[13px]">P(No-Fault-Found) for {res.nff.lru}: <b>{fmtPct(res.nff.p_nff)}</b> (threshold {fmtPct(res.nff.threshold)})</div>
                  <div className="mt-2 font-semibold" style={{ color: res.nff.p_nff >= res.nff.threshold ? "var(--serious)" : "var(--success-text)" }}>{res.nff.recommendation}</div>
                </div>
              ) : <div className="muted text-[13px]">Select the suspect LRU to get a No-Fault-Found estimate.</div>}
            </Card>
            <Card title="What fixed it before" sub={`Fleet actions in ATA ${res.ata[0].ata}, ranked by repeat-defect rate within 30 days`}>
              {res.fix_effectiveness.length ? (
                <table className="tbl"><thead><tr><th>Action</th><th className="text-right">Cases</th><th className="text-right">Repeat ≤30 d</th></tr></thead>
                  <tbody>{res.fix_effectiveness.map((f: any) => <tr key={f.action_kind}><td>{f.action_kind}</td><td className="text-right tabular">{f.cases}</td><td className="text-right tabular">{fmtPct(f.repeat_rate)}</td></tr>)}</tbody></table>
              ) : <div className="muted text-[13px]">No fleet history for this chapter.</div>}
            </Card>
          </div>
          <Card title="Similar past cases" sub="Fleet = this fleet's technical log (notional); MaintNet = real general-aviation logbook (public)">
            <div className="scroll-y max-h-[520px]">
              <table className="tbl"><thead><tr><th>Source</th><th>Problem</th><th>Action</th><th className="text-right">Match</th></tr></thead>
                <tbody>{res.similar.map((s: any) => (
                  <tr key={s.ref}><td><span className="chip">{s.source === "fleet" ? `Fleet ${s.tail}` : "MaintNet"}</span>{s.repeat_30d && <div className="text-[11px] mt-1" style={{ color: "var(--serious)" }}>repeated ≤30 d</div>}</td>
                    <td>{s.problem}</td><td className="secondary">{s.action}</td><td className="text-right tabular">{fmtPct(s.similarity)}</td></tr>))}</tbody></table>
            </div>
          </Card>
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Snags by ATA chapter (2 years)">{stats.data ? <Chart option={paretoOpt} height={Math.max(260, by.length * 22)} /> : <Loading />}</Card>
        <Card title="Recent technical-log entries">
          <div className="scroll-y max-h-[460px]">
            <table className="tbl"><thead><tr><th>Date</th><th>Tail</th><th>ATA</th><th>Snag</th><th>Finding</th></tr></thead>
              <tbody>{(recent.data || []).map((s) => <tr key={s.snag_id}><td className="tabular whitespace-nowrap">{s.date.slice(0, 10)}</td><td className="whitespace-nowrap">{s.tail}</td><td>{s.ata}</td><td>{s.text}</td><td>{s.finding}</td></tr>)}</tbody></table>
          </div>
        </Card>
      </div>
    </div>
  );
}
