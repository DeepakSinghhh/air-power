import { Upload } from "lucide-react";
import { useState } from "react";
import { Card, ErrorBox, Loading, Meter, PageHeader } from "../components/ui";
import { fmt, fmtPct, useApi } from "../lib/api";

const LAYERS: string[][] = [
  ["HUMS", "Tech log", "Flying records", "Spares ERP", "Repair agencies"],
  ["Common data model"],
  ["Engine RUL", "LRU survival", "NFF / rogue", "Snag NLP"],
  ["Fleet Twin"],
  ["FMP", "RBS", "Planner"],
  ["Command centre"],
];

export default function DataPage() {
  const { data, error } = useApi<any>("/api/data/sources");
  const [kind, setKind] = useState("snags");
  const [report, setReport] = useState<any>(null);
  const upload = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch(`/api/data/validate?kind=${kind}`, { method: "POST", body: fd });
    setReport(await r.json());
  };
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Data fabric" sub="One common data model joins health monitoring, technical records, spares and repair-agency data — aligned to ASD S5000F (in-service feedback), ATA iSpec 2200 chapters and MIMOSA OSA-CBM layers. Every source carries a quality score and lineage." />
      <Card title="Sources" sub={`Quality = completeness, cross-source consistency and freshness. Reference date ${data.today}.`}>
        <div className="scroll-y">
          <table className="tbl">
            <thead><tr><th>Source</th><th>Entity</th><th>S5000F concept</th><th>OSA-CBM</th><th className="text-right">Rows</th><th className="text-right">Complete</th><th className="text-right">Fresh</th><th className="w-[160px]">Quality</th></tr></thead>
            <tbody>{data.sources.map((s: any) => (
              <tr key={s.key}><td><b>{s.label}</b></td><td className="secondary">{s.entity}</td><td className="secondary">{s.s5000f}</td><td>{s.osa_cbm}</td>
                <td className="text-right tabular">{fmt(s.rows)}</td><td className="text-right tabular">{fmtPct(s.completeness, 1)}</td>
                <td className="text-right tabular">{s.freshness_days != null ? `${s.freshness_days} d` : "—"}</td>
                <td><div className="flex items-center gap-2"><Meter value={s.score} /><span className="tabular text-[12px]">{fmtPct(s.score)}</span></div></td></tr>))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Lineage" sub="Every number on every screen traces back through these layers">
        <div className="flex flex-col gap-2">
          {LAYERS.map((row, i) => (
            <div key={i} className="flex flex-col items-center">
              <div className="flex flex-wrap justify-center gap-2">
                {row.map((n) => <span key={n} className="chip" style={i === 3 ? { borderColor: "var(--brand)" } : undefined}>{n}</span>)}
              </div>
              {i < LAYERS.length - 1 && <div className="muted text-[12px]">↓</div>}
            </div>
          ))}
        </div>
      </Card>
      <Card title="Validate an export" sub="Drop a CSV export from e-MMS / IMMOLS-style systems; it is checked against the common data model (nothing is stored).">
        <div className="flex flex-wrap items-center gap-3">
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="snags">Snags (date, tail, text)</option><option value="stock">Stock (stock_point, lru, qty)</option><option value="sorties">Sorties (date, tail, hours)</option>
          </select>
          <label className="btn"><Upload size={14} />Choose CSV<input type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>
        </div>
        {report && (
          <div className="mt-3 text-[13px] space-y-1">
            <div><b style={{ color: report.ok ? "var(--success-text)" : "var(--critical)" }}>{report.ok ? "Accepted" : "Rejected"}</b> · {fmt(report.rows)} rows · completeness {fmtPct(report.completeness, 1)}</div>
            {report.errors?.map((e: string) => <div key={e} style={{ color: "var(--critical)" }}>✕ {e}</div>)}
            {report.warnings?.map((w: string) => <div key={w} style={{ color: "var(--serious)" }}>! {w}</div>)}
            {report.ata_preview && (
              <table className="tbl mt-2"><thead><tr><th>Text</th><th>Auto-coded ATA</th></tr></thead>
                <tbody>{report.ata_preview.map((p: any, i: number) => <tr key={i}><td>{p.text}</td><td>ATA {p.ata.ata} {p.ata.name} ({fmtPct(p.ata.p)})</td></tr>)}</tbody></table>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
