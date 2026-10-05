import { ShieldCheck } from "lucide-react";
import { Card, Chart, ErrorBox, Loading, PageHeader } from "../components/ui";
import { fmt, fmtPct, useApi } from "../lib/api";
import { grid, legend, tooltip, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

export default function ModelsPage() {
  const { tokens: t } = useTheme();
  const { data, error } = useApi<any>("/api/models");
  const audit = useApi<any>("/api/audit");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const rul = data.cards.find((c: any) => c.id === "engine_rul").metrics;
  const subsets = ["FD001", "FD002", "FD003", "FD004", "ALL"];
  const covOpt = {
    grid: grid({ top: 36 }),
    legend: legend(t, { data: ["Raw quantile model", "Conformal (calibrated)"] }),
    tooltip: tooltip(t, { valueFormatter: (v: number) => fmtPct(v, 1) }),
    xAxis: { type: "category", data: subsets, axisLabel: { color: t["text-secondary"] }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
    yAxis: yVal(t, { min: 0.6, max: 1, axisLabel: { color: t["text-muted"], formatter: (v: number) => `${Math.round(v * 100)}%` } }),
    series: [
      { name: "Raw quantile model", type: "bar", barMaxWidth: 22, data: subsets.map((s) => rul[s].picp90_uncalibrated), itemStyle: { color: t.baseline, borderRadius: [4, 4, 0, 0] } },
      { name: "Conformal (calibrated)", type: "bar", barMaxWidth: 22, data: subsets.map((s) => rul[s].picp90), itemStyle: { color: t["series-1"], borderRadius: [4, 4, 0, 0] },
        markLine: { symbol: "none", data: [{ yAxis: 0.9 }], lineStyle: { color: t["text-secondary"], type: "solid", width: 1 }, label: { color: t["text-secondary"], position: "insideStartTop", formatter: "nominal 90 %" } } },
    ],
  };
  const pts = data.calibration_points;
  const lifeOpt = {
    grid: grid({ top: 36, left: 56, bottom: 40 }),
    legend: legend(t, { data: ["Jodhpur", "Pune", "Tezpur", "Thanjavur"] }),
    tooltip: { trigger: "item", backgroundColor: t["surface-1"], borderColor: t.grid, textStyle: { color: t["text-primary"], fontSize: 12 },
      formatter: (p: any) => `<b>${p.data[2]}</b> @ ${p.seriesName}<br/>predicted ${fmt(p.data[0])} FH · true ${fmt(p.data[1])} FH` },
    xAxis: { type: "log", name: "Predicted mean life (FH)", nameLocation: "middle", nameGap: 26, axisLabel: { color: t["text-muted"] }, splitLine: { lineStyle: { color: t.grid } }, axisLine: { lineStyle: { color: t.axis } }, nameTextStyle: { color: t["text-muted"] }, min: 150, max: 6000 },
    yAxis: { type: "log", name: "True mean life (FH)", axisLabel: { color: t["text-muted"] }, splitLine: { lineStyle: { color: t.grid } }, nameTextStyle: { color: t["text-muted"] }, min: 150, max: 6000 },
    series: [
      ...["jodhpur", "pune", "tezpur", "thanjavur"].map((b, i) => ({
        name: b[0].toUpperCase() + b.slice(1), type: "scatter", symbolSize: 9,
        data: pts.filter((p: any) => p.base === b).map((p: any) => [p.pred, p.true, p.lru]),
        itemStyle: { color: t[`series-${i + 1}`], borderColor: t["surface-1"], borderWidth: 2 },
      })),
      { type: "line", data: [[150, 150], [6000, 6000]], symbol: "none", lineStyle: { color: t["text-muted"], width: 1 }, silent: true, tooltip: { show: false } },
    ],
  };
  const fl = data.federated;
  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Models & trust" sub="Model cards with data provenance and honest metrics, calibration evidence, federated learning across bases, and the hash-chained decision log." />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Engine RUL interval coverage (NASA C-MAPSS test sets)" sub="A 90 % interval should contain the true RUL 90 % of the time; conformal calibration fixes the raw model's over-confidence.">
          <Chart option={covOpt} height={280} />
        </Card>
        <Card title="Reliability models recover the hidden truth" sub="Predicted vs true mean life per LRU type and base (log scale); diagonal = perfect">
          <Chart option={lifeOpt} height={280} />
        </Card>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
        {data.cards.map((c: any) => (
          <Card key={c.id} title={c.name} sub={`Data: ${c.data}`}>
            <div className="text-[12.5px] space-y-1.5">
              <div><span className="muted">Intended use:</span> {c.intended_use}</div>
              <div><span className="muted">Limitations:</span> {c.limits}</div>
              <MetricList m={c.metrics} />
            </div>
          </Card>
        ))}
      </div>
      {fl && (
        <Card title="Federated learning across bases" sub={fl.description}>
          <table className="tbl"><thead><tr><th>Training regime</th><th className="text-right">RMSE (cycles)</th><th>Raw data leaves base?</th></tr></thead>
            <tbody>{fl.results.map((r: any) => <tr key={r.regime}><td>{r.regime}</td><td className="text-right tabular">{fmt(r.rmse, 2)}</td><td>{r.data_moved}</td></tr>)}</tbody></table>
        </Card>
      )}
      <Card title="Decision audit log" sub="Append-only, SHA-256 hash-chained. Any edit to an earlier entry breaks verification."
        right={audit.data && <span className="chip"><ShieldCheck size={13} style={{ color: audit.data.verify.ok ? "var(--good)" : "var(--critical)" }} />{audit.data.verify.ok ? `Chain verified · ${audit.data.verify.entries} entries` : `Broken at #${audit.data.verify.broken_at}`}</span>}>
        {!audit.data?.entries?.length ? <div className="muted text-sm">No decisions recorded yet — approve a plan in the Readiness planner.</div> : (
          <table className="tbl"><thead><tr><th>#</th><th>Time (UTC)</th><th>Persona</th><th>Decision</th><th>Summary</th><th>Hash</th></tr></thead>
            <tbody>{[...audit.data.entries].reverse().map((e: any) => (
              <tr key={e.seq}><td className="tabular">{e.seq}</td><td className="tabular">{e.ts}</td><td>{e.persona}</td><td>{e.decision}</td><td>{e.summary}</td><td className="tabular text-[11px]">{e.hash.slice(0, 12)}…</td></tr>))}</tbody></table>
        )}
      </Card>
    </div>
  );
}

function MetricList({ m }: { m: any }) {
  if (!m) return null;
  const flat: [string, any][] = [];
  const walk = (o: any, p = "") => Object.entries(o).forEach(([k, v]) => {
    if (k === "per_lru") return;
    if (v && typeof v === "object" && !Array.isArray(v)) walk(v, `${p}${k} · `);
    else if (typeof v === "number") flat.push([`${p}${k}`, v]);
  });
  walk(m);
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-2">
      {flat.slice(0, 14).map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2 text-[11.5px]"><span className="muted truncate">{k.replaceAll("_", " ")}</span><span className="tabular">{Number.isInteger(v) ? fmt(v) : Math.abs(v) <= 1 ? v.toFixed(3) : fmt(v, 1)}</span></div>
      ))}
    </div>
  );
}
