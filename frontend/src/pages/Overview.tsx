import { ArrowRight, Boxes, Plane, Repeat, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, Chart, ErrorBox, Loading, PageHeader, StateBar, StateChip, StateLegend } from "../components/ui";
import { fmt, fmtPct, useApi } from "../lib/api";
import { fanSeries, grid, legend, tooltip, xCat, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

export default function Overview() {
  const { tokens: t } = useTheme();
  const { data, error } = useApi<any>("/api/overview");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const fb = data.forecast.baseline;
  const ft = data.forecast.tatpar;
  const days = fb ? fb.p50.map((_: number, i: number) => `D+${i}`) : [];
  const h = data.headline;
  const cal = data.forecast.calibration;

  const fanOpt = fb && {
    grid: grid({ top: 40 }),
    legend: legend(t, { data: ["Current practice", "With TATPAR"] }),
    tooltip: tooltip(t, {
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex;
        return `<b>${days[i]}</b><br/>Current practice <b>${fb.p50[i].toFixed(0)}</b> (P10–P90 ${fb.p10[i].toFixed(0)}–${fb.p90[i].toFixed(0)})<br/>` +
          `With TATPAR <b>${ft.p50[i].toFixed(0)}</b> (P10–P90 ${ft.p10[i].toFixed(0)}–${ft.p90[i].toFixed(0)})`;
      },
    }),
    xAxis: xCat(t, days, { axisLabel: { color: t["text-muted"], interval: 9 } }),
    yAxis: yVal(t, { min: 20, max: 52 }),
    series: [...fanSeries("Current practice", t.baseline, fb, "b"), ...fanSeries("With TATPAR", t["series-1"], ft, "t")],
  };

  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Command overview"
        sub="How many aircraft will be mission-capable, how sure we are, and what to do about it. Forecasts are Monte-Carlo runs of the Fleet Twin using only model predictions." />

      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_2fr] gap-4">
        <div className="card card-pad flex flex-col justify-between">
          <div>
            <div className="h-sub">Mission-capable now</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-[56px] font-semibold leading-none">{data.mc_now}</span>
              <span className="text-[20px] secondary">/ {data.n_tails}</span>
              <span className="ml-2 text-[15px] secondary">{fmtPct(data.mc_now / data.n_tails)}</span>
            </div>
            <div className="mt-3"><StateBar states={data.states} total={data.n_tails} /></div>
            <div className="mt-2"><StateLegend /></div>
          </div>
          <div className="grid grid-cols-2 gap-3 mt-5">
            <div>
              <div className="h-sub">D+30 forecast · current practice</div>
              <div className="text-[22px] font-semibold tabular">{fmt(fb?.p50[30])} <span className="text-[13px] secondary">({fmt(fb?.p10[30])}–{fmt(fb?.p90[30])})</span></div>
            </div>
            <div>
              <div className="h-sub">D+30 forecast · with TATPAR</div>
              <div className="text-[22px] font-semibold tabular">{fmt(ft?.p50[30])} <span className="text-[13px] secondary">({fmt(ft?.p10[30])}–{fmt(ft?.p90[30])})</span></div>
            </div>
            <div className="col-span-2 rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="text-[13px]">
                Full TATPAR policy over one year: <b>{h.delta != null ? `+${(h.delta * 100).toFixed(1)} pts` : "—"}</b> mission-capable
                (±{h.ci != null ? (h.ci * 100).toFixed(1) : "—"}), ≈ <b>{fmt(h.aircraft)} more aircraft every day</b> from the same fleet and spares budget.
              </div>
              <div className="text-[11.5px] muted mt-1">Evaluated against hidden ground truth with common random numbers · <Link to="/loss">see lever breakdown</Link></div>
            </div>
          </div>
        </div>
        <Card title="Readiness forecast — mission-capable aircraft, next 60 days" sub={cal ? `Shaded: P10–P90. Calibration check: the 80 % band contained ${fmtPct(cal.coverage_p10_p90)} of true outcomes. Weekly rhythm: aircraft recover at weekends.` : undefined}>
          {fanOpt && <Chart option={fanOpt} height={300} />}
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {data.squadrons.map((s: any) => (
          <div key={s.id} className="card card-pad">
            <div className="flex items-center justify-between">
              <div className="h-title">{s.name}</div>
              <span className="text-[22px] font-semibold tabular">{s.mc_now}<span className="text-[13px] secondary">/{s.n}</span></span>
            </div>
            <div className="mt-2"><StateBar states={s.states} total={s.n} /></div>
            <div className="grid grid-cols-2 gap-2 mt-3 text-[12px]">
              <div><div className="muted">D+30 current</div><div className="tabular font-semibold">{s.d30_baseline ? `${s.d30_baseline[1]} (${s.d30_baseline[0]}–${s.d30_baseline[2]})` : "—"}</div></div>
              <div><div className="muted">D+30 TATPAR</div><div className="tabular font-semibold">{s.d30_tatpar ? `${s.d30_tatpar[1]} (${s.d30_tatpar[0]}–${s.d30_tatpar[2]})` : "—"}</div></div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Highest snag risk — next 7 days" sub="P(at least one LRU failure), from survival models with base environment and mission severity">
          <table className="tbl">
            <thead><tr><th>Tail</th><th>Sqn</th><th>Status</th><th className="text-right">P(snag 7d)</th></tr></thead>
            <tbody>
              {data.top_risks.map((r: any) => (
                <tr key={r.tail}>
                  <td><Link to={`/aircraft/${r.tail}`}>{r.tail}</Link></td><td>{r.squadron}</td>
                  <td><StateChip state={r.state} /></td><td className="text-right tabular">{fmtPct(r.p_snag_7d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Engine watch" sub="Lowest calibrated remaining life (median, flight hours) from HUMS">
          <table className="tbl">
            <thead><tr><th>Tail</th><th>Sqn</th><th className="text-right">Engine RUL (FH)</th><th className="text-right">To phase (FH)</th></tr></thead>
            <tbody>
              {data.engine_watch.map((r: any) => (
                <tr key={r.tail}>
                  <td><Link to={`/aircraft/${r.tail}`}>{r.tail}</Link></td><td>{r.squadron}</td>
                  <td className="text-right tabular">{fmt(r.engine_rul_fh_min)}</td><td className="text-right tabular">{fmt(r.to_phase)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Action queue" sub="Recommendations waiting for a decision">
          <div className="space-y-2">
            <ActionRow icon={<Repeat size={16} />} label="Predictive spares transfers" n={data.actions.transfers} to="/sustainment" />
            <ActionRow icon={<Plane size={16} />} label="Aircraft on ground awaiting a part" n={data.actions.aog} to="/sustainment" />
            <ActionRow icon={<Wrench size={16} />} label="Depot repairs to expedite" n={data.actions.expedite} to="/sustainment" />
            <ActionRow icon={<Boxes size={16} />} label="Plan a readiness requirement" n={null} to="/planner" />
          </div>
        </Card>
      </div>

      <Card title="Base environmental severity" sub="Real CAMS 2024 dust (Open-Meteo) + climatology. Indices feed the reliability models; Leh shown for detachment planning.">
        <table className="tbl">
          <thead><tr><th>Base</th><th>Climate</th><th className="text-right">Dust µg/m³</th><th className="text-right">Dust idx</th><th className="text-right">Heat idx</th><th className="text-right">Humidity idx</th><th className="text-right">Altitude idx</th><th className="text-right">Severity</th></tr></thead>
          <tbody>
            {data.environment.map((b: any) => (
              <tr key={b.base}><td>{b.name}</td><td className="secondary">{b.climate}</td><td className="text-right tabular">{fmt(b.dust_ugm3, 1)}</td>
                <td className="text-right tabular">{fmt(b.dust, 2)}</td><td className="text-right tabular">{fmt(b.heat, 2)}</td><td className="text-right tabular">{fmt(b.hum, 2)}</td>
                <td className="text-right tabular">{fmt(b.alt, 2)}</td><td className="text-right tabular font-semibold">×{fmt(b.severity_index, 2)}</td></tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function ActionRow({ icon, label, n, to }: { icon: React.ReactNode; label: string; n: number | null; to: string }) {
  return (
    <Link to={to} className="flex items-center gap-3 rounded-lg px-3 py-2.5 no-underline" style={{ background: "var(--surface-2)", color: "var(--text-primary)" }}>
      <span style={{ color: "var(--brand)" }}>{icon}</span>
      <span className="flex-1 text-[13px]">{label}</span>
      {n != null && <span className="text-[18px] font-semibold tabular">{n}</span>}
      <ArrowRight size={14} className="muted" />
    </Link>
  );
}
