import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, Chart, ErrorBox, Loading, PageHeader, StateChip } from "../components/ui";
import { fmt, fmtPct, useApi } from "../lib/api";
import { grid, legend, tooltip, yVal } from "../lib/charts";
import { useTheme, type Tokens } from "../lib/theme";

export default function AircraftPage() {
  const { tail } = useParams();
  const fleet = useApi<any[]>("/api/fleet");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"risk" | "tail" | "phase">("risk");
  const nav = useNavigate();
  const rows = useMemo(() => {
    let r = (fleet.data || []).filter((x) => !q || x.tail.toLowerCase().includes(q.toLowerCase()) || x.squadron.toLowerCase().includes(q.toLowerCase()));
    r = [...r].sort((a, b) => sort === "risk" ? b.p_snag_7d - a.p_snag_7d : sort === "phase" ? a.to_phase - b.to_phase : a.tail.localeCompare(b.tail));
    return r;
  }, [fleet.data, q, sort]);
  if (fleet.error) return <ErrorBox error={fleet.error} />;
  if (!fleet.data) return <Loading />;
  return (
    <div className="space-y-4 max-w-[1500px]">
      <PageHeader title="Aircraft health" sub="Every tail with its status, hours to each check, short-term snag risk, engine remaining life and leak flags. Select a tail for its digital record." />
      <div className="grid grid-cols-1 2xl:grid-cols-[540px_1fr] gap-4">
        <Card title="Fleet register" right={<div className="flex gap-2">
          <input className="input w-[140px]" placeholder="Filter tail / sqn" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value as any)}>
            <option value="risk">Sort: risk</option><option value="phase">Sort: hours to phase</option><option value="tail">Sort: tail</option>
          </select></div>}>
          <div className="scroll-y max-h-[720px]">
            <table className="tbl">
              <thead><tr><th>Tail</th><th>Status</th><th className="text-right">To phase</th><th className="text-right">P(snag 7d)</th><th className="text-right">Engine RUL</th><th>Flags</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.tail} onClick={() => nav(`/aircraft/${r.tail}`)} style={{ cursor: "pointer", background: r.tail === tail ? "var(--surface-2)" : undefined }}>
                    <td><b>{r.tail}</b><div className="muted text-[11px]">{r.squadron}</div></td>
                    <td><StateChip state={r.state} /></td>
                    <td className="text-right tabular">{fmt(r.to_phase)} FH</td>
                    <td className="text-right tabular">{fmtPct(r.p_snag_7d)}</td>
                    <td className="text-right tabular">{r.engine_rul_fh_min != null ? `${fmt(r.engine_rul_fh_min)} FH` : "—"}</td>
                    <td className="text-[11px]">{r.chronic && <span className="chip">Chronic</span>} {r.rogue_parts > 0 && <span className="chip">Rogue part</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        {tail ? <Detail tail={tail} /> : <Card title="Select an aircraft"><div className="muted text-sm">Choose a tail from the register to open its health record.</div></Card>}
      </div>
    </div>
  );
}

const ZONES: { key: string; label: string; x: number; y: number; atas: number[] }[] = [
  { key: "nose", label: "Radar & nav", x: 200, y: 38, atas: [34] },
  { key: "cockpit", label: "Cockpit / displays / escape", x: 200, y: 98, atas: [31, 25, 23] },
  { key: "lwing", label: "Flight controls & fuel", x: 92, y: 238, atas: [27, 28] },
  { key: "centre", label: "Hydraulics, electrics, ECS", x: 200, y: 190, atas: [29, 24, 21, 36] },
  { key: "gear", label: "Landing gear", x: 300, y: 238, atas: [32] },
  { key: "aft", label: "Engines & GTS", x: 200, y: 300, atas: [72, 73, 77, 79, 49] },
];

const riskColor = (t: Tokens, p: number) => (p < 0.1 ? t.good : p < 0.25 ? t.warning : p < 0.5 ? t.serious : t.critical);
const riskLabel = (p: number) => (p < 0.1 ? "Low" : p < 0.25 ? "Elevated" : p < 0.5 ? "High" : "Critical");

function Schematic({ lrus }: { lrus: any[] }) {
  const { tokens: t } = useTheme();
  const zoneRisk = ZONES.map((z) => {
    const items = lrus.filter((l) => z.atas.includes(l.ata));
    const p = 1 - items.reduce((acc, l) => acc * (1 - l.p_fail_30d), 1);
    const missing = items.some((l) => l.missing);
    return { ...z, p, missing, top: [...items].sort((a, b) => b.p_fail_30d - a.p_fail_30d)[0] };
  });
  return (
    <div className="flex flex-col md:flex-row gap-4 items-start">
      <svg viewBox="0 0 400 360" className="w-full max-w-[340px]" role="img" aria-label="Aircraft schematic coloured by 30-day failure risk per zone">
        <g fill="var(--surface-2)" stroke="var(--axis)" strokeWidth="1.5">
          <path d="M200 12 C214 40 218 80 218 120 L218 300 L232 336 L168 336 L182 300 L182 120 C182 80 186 40 200 12 Z" />
          <path d="M182 150 L30 262 L30 282 L182 236 Z" />
          <path d="M218 150 L370 262 L370 282 L218 236 Z" />
          <path d="M184 276 L130 330 L132 342 L188 312 Z" />
          <path d="M216 276 L270 330 L268 342 L212 312 Z" />
          <ellipse cx="200" cy="96" rx="10" ry="26" fill="var(--grid)" />
        </g>
        {zoneRisk.map((z) => (
          <g key={z.key}>
            <circle cx={z.x} cy={z.y} r="15" fill={riskColor(t, z.p)} stroke="var(--surface-1)" strokeWidth="2" />
            {z.missing && <circle cx={z.x} cy={z.y} r="21" fill="none" stroke={t.critical} strokeWidth="2" />}
            <text x={z.x} y={z.y + 4} textAnchor="middle" fontSize="10" fontWeight="700" fill="#0b0b0b">{Math.round(z.p * 100)}</text>
          </g>
        ))}
      </svg>
      <div className="flex-1 text-[12.5px] space-y-1.5">
        <div className="muted">Zone risk = P(any LRU in the zone fails in 30 days), %. Ring = part missing (awaiting spares).</div>
        {zoneRisk.map((z) => (
          <div key={z.key} className="flex items-center gap-2">
            <span className="dot" style={{ background: riskColor(t, z.p) }} />
            <span className="w-[190px]">{z.label}</span>
            <span className="tabular font-semibold w-[44px] text-right">{fmtPct(z.p)}</span>
            <span className="muted">{riskLabel(z.p)}{z.top ? ` · top: ${z.top.name}` : ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Detail({ tail }: { tail: string }) {
  const { tokens: t } = useTheme();
  const { data, error, loading } = useApi<any>(`/api/aircraft/${tail}`);
  if (error) return <ErrorBox error={error} />;
  if (!data || data.tail !== tail) return <Card title={tail}><Loading label="Computing HUMS predictions…" /></Card>;
  return (
    <div className={`space-y-4 ${loading ? "opacity-60" : ""}`}>
      <div className="card card-pad">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-[20px] font-bold m-0">{data.tail}</h2>
          <StateChip state={data.state} />
          <span className="secondary text-[13px]">{data.type_label} · {data.squadron} · {data.base}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3 text-[12.5px]">
          <KV k="Airframe hours" v={`${fmt(data.hours_total)} FH`} />
          <KV k="To minor check" v={`${fmt(data.to_minor)} FH`} />
          <KV k="To phase check" v={`${fmt(data.to_phase)} FH`} />
          <KV k="To depot overhaul" v={`${fmt(data.to_overhaul)} FH`} />
          <KV k="P(snag, 7 days)" v={fmtPct(data.p_snag_7d)} />
        </div>
      </div>
      <Card title="Digital record — risk by zone"><Schematic lrus={data.lrus} /></Card>
      {data.engines.map((e: any, i: number) => <EngineCard key={e.pos} e={e} idx={i + 1} t={t} />)}
      <Card title="Installed LRUs" sub="Conditional failure probability from the Weibull AFT models (base environment + mission severity)">
        <div className="scroll-y max-h-[360px]">
          <table className="tbl">
            <thead><tr><th>LRU</th><th>ATA</th><th>Serial</th><th className="text-right">Hours since repair</th><th className="text-right">P(fail 7d)</th><th className="text-right">P(fail 30d)</th></tr></thead>
            <tbody>
              {[...data.lrus].sort((a: any, b: any) => b.p_fail_30d - a.p_fail_30d).map((l: any) => (
                <tr key={l.pos}>
                  <td>{l.name}</td><td className="tabular">{l.ata}</td>
                  <td className="tabular">{l.missing ? <span className="chip"><span className="dot" style={{ background: t.critical }} />Missing</span> : l.serial}</td>
                  <td className="text-right tabular">{fmt(l.hours_since_repair)}</td>
                  <td className="text-right tabular">{fmtPct(l.p_fail_7d, 1)}</td>
                  <td className="text-right tabular"><span className="dot mr-1.5" style={{ background: riskColor(t, l.p_fail_30d) }} />{fmtPct(l.p_fail_30d, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Technical log" sub={data.chronic.length ? `Chronic defect: ATA ${data.chronic.map((c: any) => c.ata).join(", ")} — repeated snags within 30 days` : "Most recent snags"}>
        <div className="scroll-y max-h-[320px]">
          <table className="tbl">
            <thead><tr><th>Date</th><th>ATA</th><th>Snag</th><th>Action</th><th>Finding</th></tr></thead>
            <tbody>{data.snags.map((s: any) => (
              <tr key={s.snag_id}><td className="tabular whitespace-nowrap">{s.date.slice(0, 10)}</td><td>{s.ata}</td><td>{s.text}</td><td className="secondary">{s.action}</td><td>{s.finding}</td></tr>))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return <div><div className="muted">{k}</div><div className="font-semibold tabular text-[15px]">{v}</div></div>;
}

function EngineCard({ e, idx, t }: { e: any; idx: number; t: Tokens }) {
  const xs = e.trend.map((p: any) => p.cycle);
  const trendOpt = {
    grid: grid({ top: 34 }),
    legend: legend(t, { data: ["Median RUL", "90 % interval (conformal)"] }),
    tooltip: tooltip(t, { formatter: (ps: any[]) => { const p = e.trend[ps[0].dataIndex]; return `Cycle <b>${p.cycle}</b><br/>RUL <b>${p.med.toFixed(0)}</b> cycles (${p.lo.toFixed(0)}–${p.hi.toFixed(0)})`; } }),
    xAxis: { type: "category", data: xs, boundaryGap: false, axisLabel: { color: t["text-muted"] }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false }, name: "HUMS cycle", nameTextStyle: { color: t["text-muted"] } },
    yAxis: yVal(t, { name: "RUL (cycles)" }),
    series: [
      { type: "line", data: e.trend.map((p: any) => p.lo), stack: "b", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true, tooltip: { show: false } },
      { name: "90 % interval (conformal)", type: "line", data: e.trend.map((p: any) => p.hi - p.lo), stack: "b", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: t["series-1"], opacity: 0.14 }, itemStyle: { color: t["series-1"] }, silent: true },
      { name: "Median RUL", type: "line", data: e.trend.map((p: any) => p.med), symbol: "none", lineStyle: { color: t["series-1"], width: 2 }, itemStyle: { color: t["series-1"] } },
    ],
  };
  const mods = Object.entries(e.modules as Record<string, number>).filter(([k]) => k !== "Usage / age");
  const modOpt = {
    grid: grid({ left: 110, top: 8, right: 40, bottom: 24 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => `<b>${p.value.toFixed(1)}</b> cycles of RUL<br/>${p.name}` }),
    xAxis: yVal(t, { name: "SHAP (cycles of RUL)" }),
    yAxis: { type: "category", data: mods.map(([k]) => k), axisLabel: { color: t["text-secondary"] }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar", barWidth: 14, data: mods.map(([, v]) => ({ value: v, itemStyle: { color: v < 0 ? t["series-2"] : t["series-1"], borderRadius: v < 0 ? [4, 0, 0, 4] : [0, 4, 4, 0] } })) }],
  };
  return (
    <Card title={`Engine ${idx} — RUL ${fmt(e.rul_fh.med)} FH (90 %: ${fmt(e.rul_fh.lo)}–${fmt(e.rul_fh.hi)} FH)`}
      sub={`HUMS stream: ${e.hums_source}, cycle ${e.cycle}. Interval calibrated by conformal prediction; degradation attributed to modules with SHAP.`}>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Chart option={trendOpt} height={230} />
        <div>
          <div className="h-sub mb-1">Where is the degradation? (negative = shortening life)</div>
          <Chart option={modOpt} height={200} />
        </div>
      </div>
    </Card>
  );
}
