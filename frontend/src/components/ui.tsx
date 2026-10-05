import ReactECharts from "echarts-for-react";
import type { ReactNode } from "react";
import { STATE_LABEL, stateColor, useTheme } from "../lib/theme";

export function Card({ title, sub, right, children, className = "", pad = true }: {
  title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={`card ${pad ? "card-pad" : ""} ${className}`}>
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 mb-3">
          <div>
            {title && <h2 className="h-title m-0">{title}</h2>}
            {sub && <p className="h-sub m-0 mt-0.5">{sub}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: string }) {
  return (
    <div className="card card-pad">
      <div className="h-sub">{label}</div>
      <div className="text-[28px] font-semibold leading-tight mt-1" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      {sub && <div className="text-[12px] secondary mt-1">{sub}</div>}
    </div>
  );
}

export function Chart({ option, height = 260, onEvents }: { option: object; height?: number; onEvents?: Record<string, (p: any) => void> }) {
  const { dark } = useTheme();
  return (
    <ReactECharts
      option={{ backgroundColor: "transparent", animationDuration: 300, ...option }}
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
      theme={dark ? "dark" : undefined}
      onEvents={onEvents}
    />
  );
}

export function StateChip({ state }: { state: string }) {
  const { tokens } = useTheme();
  return (
    <span className="chip">
      <span className="dot" style={{ background: stateColor(tokens, state) }} />
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

export function StateBar({ states, total }: { states: Record<string, number>; total: number }) {
  const { tokens } = useTheme();
  const order = ["MC", "NMCS", "NMCM_U", "NMCM_S", "DEPOT", "WAIT"];
  return (
    <div className="flex h-3 w-full gap-[2px] rounded overflow-hidden" role="img"
         aria-label={order.map((s) => `${STATE_LABEL[s]} ${states[s] ?? 0}`).join(", ")}>
      {order.map((s) => (states[s] ?? 0) > 0 && (
        <div key={s} title={`${STATE_LABEL[s]}: ${states[s]}`} style={{ width: `${((states[s] ?? 0) / total) * 100}%`, background: stateColor(tokens, s) }} />
      ))}
    </div>
  );
}

export function StateLegend() {
  const { tokens } = useTheme();
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] secondary">
      {["MC", "NMCS", "NMCM_U", "NMCM_S", "DEPOT", "WAIT"].map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ background: stateColor(tokens, s) }} />
          {STATE_LABEL[s]}
        </span>
      ))}
    </div>
  );
}

export function Meter({ value, color }: { value: number; color?: string }) {
  const { tokens } = useTheme();
  const c = color ?? (value >= 0.8 ? tokens.good : value >= 0.6 ? tokens.warning : tokens.critical);
  return (
    <div className="h-2 w-full rounded-full" style={{ background: "var(--surface-2)" }}>
      <div className="h-2 rounded-full" style={{ width: `${Math.max(2, Math.min(100, value * 100))}%`, background: c }} />
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="muted text-sm p-6">{label}</div>;
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="card card-pad text-sm" style={{ color: "var(--critical)" }}>Could not load: {error}</div>;
}

export function PageHeader({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
      <div>
        <h1 className="text-[22px] font-bold m-0">{title}</h1>
        {sub && <p className="secondary text-[13.5px] m-0 mt-1 max-w-[860px]">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function Pill({ children, tone }: { children: ReactNode; tone?: "good" | "warning" | "critical" | "brand" }) {
  const map: Record<string, string> = { good: "var(--good)", warning: "var(--warning)", critical: "var(--critical)", brand: "var(--brand)" };
  return (
    <span className="chip">
      {tone && <span className="dot" style={{ background: map[tone] }} />}
      {children}
    </span>
  );
}
