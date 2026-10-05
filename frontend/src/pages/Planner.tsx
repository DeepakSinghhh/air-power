import { CheckCircle2, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { usePersona } from "../components/Layout";
import { Card, Chart, ErrorBox, Loading, PageHeader } from "../components/ui";
import { fmt, fmtPct, postJSON, useApi } from "../lib/api";
import { fanSeries, grid, legend, tooltip, xCat, yVal } from "../lib/charts";
import { useTheme } from "../lib/theme";

const SQNS = ["SQN-A", "SQN-B", "SQN-C", "SQN-D"];

export default function PlannerPage() {
  const { tokens: t } = useTheme();
  const { persona } = usePersona();
  const demo = useApi<any>("/api/requirement/demo");
  const [res, setRes] = useState<any>(null);
  const [form, setForm] = useState({ sqn: "SQN-A", start: 14, end: 17, min_mc: 9, surge: 1.2, reps: 80 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [approved, setApproved] = useState<any>(null);
  useEffect(() => {
    if (demo.data && !res) setRes(demo.data);
  }, [demo.data]);

  const run = async () => {
    setBusy(true);
    setErr(null);
    setApproved(null);
    try {
      setRes(await postJSON("/api/requirement", form));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    const final = res.steps[res.steps.length - 1];
    const e = await postJSON("/api/approve", {
      persona, kind: "readiness_plan",
      summary: `${res.squadron}: ≥${res.min_mc} MC ${res.window.start_date}→${res.window.end_date}; P(meet) ${fmtPct(res.steps[0].p_meet)} → ${fmtPct(final.p_meet)}`,
      payload: { requirement: { squadron: res.squadron, window: res.window, min_mc: res.min_mc, surge: res.surge },
                 actions: res.steps.map((s: any) => ({ lever: s.lever, gain: s.gain, details: s.details.length })) },
    });
    setApproved(e);
  };

  if (demo.error) return <ErrorBox error={demo.error} />;
  if (!res) return <Loading />;
  const steps = res.steps;
  const first = steps[0];
  const last = steps[steps.length - 1];
  const H = first.bands.p50.length;
  const days = Array.from({ length: H }, (_, i) => `D+${i}`);
  const reqLine = days.map((_, i) => (i >= res.window.start && i <= res.window.end ? res.min_mc : null));

  const barOpt = {
    grid: grid({ left: 270, top: 10, right: 60, bottom: 20 }),
    tooltip: tooltip(t, { trigger: "item", formatter: (p: any) => `<b>${fmtPct(p.value)}</b> P(meet)<br/>${p.name}` }),
    xAxis: yVal(t, { max: 1, axisLabel: { color: t["text-muted"], formatter: (v: number) => `${v * 100}%` } }),
    yAxis: { type: "category", inverse: true, data: steps.map((s: any) => s.label), axisLabel: { color: t["text-secondary"], fontSize: 12, width: 260, overflow: "break" }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: "bar", barWidth: 18, data: steps.map((s: any, i: number) => ({ value: s.p_meet, itemStyle: { color: i === 0 ? t.baseline : t["series-1"], borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: t["text-primary"], formatter: (p: any) => fmtPct(p.value) },
    }],
  };
  const fanOpt = {
    grid: grid({ top: 40 }),
    legend: legend(t, { data: ["Current practice", "With actions", "Requirement"] }),
    tooltip: tooltip(t, {
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex;
        return `<b>${days[i]}</b><br/>Current practice <b>${first.bands.p50[i].toFixed(0)}</b> (${first.bands.p10[i].toFixed(0)}–${first.bands.p90[i].toFixed(0)})<br/>With actions <b>${last.bands.p50[i].toFixed(0)}</b> (${last.bands.p10[i].toFixed(0)}–${last.bands.p90[i].toFixed(0)})` +
          (reqLine[i] != null ? `<br/>Requirement ≥ <b>${res.min_mc}</b>` : "");
      },
    }),
    xAxis: xCat(t, days, { axisLabel: { color: t["text-muted"], interval: 3 } }),
    yAxis: yVal(t, { name: "Mission-capable", min: 0, max: 16 }),
    series: [
      ...fanSeries("Current practice", t.baseline, first.bands, "a"),
      ...fanSeries("With actions", t["series-1"], last.bands, "b"),
      { name: "Requirement", type: "line", data: reqLine, symbol: "none", lineStyle: { color: t.critical, width: 2, type: "solid" }, itemStyle: { color: t.critical } },
    ],
  };

  return (
    <div className="space-y-4 max-w-[1400px]">
      <PageHeader title="Readiness planner"
        sub="State the requirement; TATPAR works backwards. Each action is scored by Monte-Carlo in the Fleet Twin on the same random futures, so the gain shown is the action's own contribution." />

      <Card title="Requirement">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[12px] secondary flex flex-col gap-1">Squadron
            <select className="input" value={form.sqn} onChange={(e) => setForm({ ...form, sqn: e.target.value })}>{SQNS.map((s) => <option key={s}>{s}</option>)}</select>
          </label>
          <Num label="From day (D+)" v={form.start} on={(v) => setForm({ ...form, start: v })} min={0} max={40} />
          <Num label="To day (D+)" v={form.end} on={(v) => setForm({ ...form, end: v })} min={0} max={45} />
          <Num label="Min mission-capable" v={form.min_mc} on={(v) => setForm({ ...form, min_mc: v })} min={1} max={16} />
          <Num label="Flying task ×" v={form.surge} on={(v) => setForm({ ...form, surge: v })} min={0.5} max={2} step={0.1} />
          <Num label="Futures" v={form.reps} on={(v) => setForm({ ...form, reps: v })} min={20} max={200} step={20} />
          <button className="btn btn-primary" onClick={run} disabled={busy}><Play size={14} />{busy ? "Planning… (~10 s)" : "Plan"}</button>
          {err && <span className="text-[12px]" style={{ color: "var(--critical)" }}>{err}</span>}
        </div>
      </Card>

      <div className={`grid grid-cols-1 xl:grid-cols-[1fr_1.3fr] gap-4 ${busy ? "opacity-60" : ""}`}>
        <Card title={`P(meet): ${fmtPct(first.p_meet)} → ${fmtPct(last.p_meet)}`}
          sub={`${res.squadron_name}: ≥${res.min_mc} mission-capable every day ${res.window.start_date} → ${res.window.end_date} (D+${res.window.start}–D+${res.window.end}), flying task ×${res.surge}. ${res.reps} futures.`}>
          <Chart option={barOpt} height={230} />
        </Card>
        <Card title="Squadron readiness forecast" sub="Median and P10–P90 band before and after the recommended actions">
          <Chart option={fanOpt} height={260} />
        </Card>
      </div>

      <Card title="Recommended actions" sub="Approve to record the decision in the hash-chained audit log"
        right={<button className="btn btn-primary" onClick={approve} disabled={!!approved}><CheckCircle2 size={14} />{approved ? "Approved" : `Approve as ${persona}`}</button>}>
        {approved && <div className="text-[12px] mb-3 secondary">Logged #{approved.seq} · hash <code>{approved.hash.slice(0, 16)}…</code></div>}
        <div className="space-y-3">
          {steps.slice(1).map((s: any) => (
            <div key={s.lever} className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-semibold text-[14px]">{s.label}</div>
                <div className="text-[13px] tabular">P(meet) {fmtPct(s.p_meet)} · <b style={{ color: s.gain >= 0 ? "var(--success-text)" : "var(--critical)" }}>{s.gain >= 0 ? "+" : ""}{(s.gain * 100).toFixed(0)} pts</b> · mean MC in window {fmt(s.mean_mc_window, 1)}</div>
              </div>
              <Details d={s.details} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Details({ d }: { d: any[] }) {
  if (!d.length) return null;
  const by: Record<string, any[]> = {};
  d.forEach((x) => (by[x.type] = [...(by[x.type] || []), x]));
  return (
    <div className="mt-2 grid gap-2 text-[12.5px] secondary">
      {by.phase && <div><b>Phase checks:</b> {by.phase.map((x) => `${x.tail} at ${x.phase_start}`).join(" · ")}</div>}
      {by.engine_protect && <div><b>Engine protection (fly ≤ conformal lower bound until swap):</b> {by.engine_protect.map((x) => `${x.tail} (${x.reason})`).join(" · ")}</div>}
      {by.transfer && <div><b>Transfers:</b> {by.transfer.map((x) => `${x.qty}× ${x.name} ${x.from}→${x.to}`).join(" · ")}</div>}
      {by.expedite && <div><b>Expedite at depot:</b> {by.expedite.map((x) => `${x.name} S/N ${x.serial} (${x.agency}, due ${x.return_in_days} d)`).join(" · ")}</div>}
      {by.policy && <div><b>Policy:</b> {by.policy.map((x) => x.text).join(" · ")}</div>}
    </div>
  );
}

function Num({ label, v, on, min, max, step = 1 }: { label: string; v: number; on: (v: number) => void; min: number; max: number; step?: number }) {
  return (
    <label className="text-[12px] secondary flex flex-col gap-1">{label}
      <input className="input w-[110px] tabular" type="number" value={v} min={min} max={max} step={step} onChange={(e) => on(Number(e.target.value))} />
    </label>
  );
}
