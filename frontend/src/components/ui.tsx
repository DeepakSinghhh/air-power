import type { ReactNode } from "react";
import { STATE_CODE, STATE_LABEL, STATE_ORDER, stateCss } from "../lib/theme";

/** Square panel with an olive label plate. */
export function Panel({ title, meta, children, className = "", pad = true, style }: {
  title: ReactNode; meta?: ReactNode; children: ReactNode; className?: string; pad?: boolean; style?: React.CSSProperties;
}) {
  return (
    <section className={`panel ${className}`} style={style}>
      <div className="lp"><span>{title}</span>{meta && <span className="meta">{meta}</span>}</div>
      <div className={pad ? "pad" : ""}>{children}</div>
    </section>
  );
}

/** Board header: number, name, one-line purpose. */
export function Board({ no, title, sub, right, children }: { no: string; title: string; sub?: ReactNode; right?: ReactNode; children: ReactNode }) {
  return (
    <div className="max-w-[1480px] mx-auto">
      <header className="boardhead">
        <div>
          <h1><em>{no}</em>{title}</h1>
          {sub && <p>{sub}</p>}
        </div>
        {right}
      </header>
      {children}
    </div>
  );
}

export function Code({ state, wide }: { state: string; wide?: boolean }) {
  return (
    <span className="code" style={{ background: stateCss(state), minWidth: wide ? 40 : undefined }} title={STATE_LABEL[state]}>
      {STATE_CODE[state] ?? state}
    </span>
  );
}

/** State code + word, for tables. */
export function StateCell({ state }: { state: string }) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <Code state={state} />
      <span className="text-[12px] ink-2">{STATE_LABEL[state] ?? state}</span>
    </span>
  );
}

export function StateBar({ states, total, height = 14 }: { states: Record<string, number>; total: number; height?: number }) {
  return (
    <div className="flex w-full gap-[2px]" style={{ height }} role="img"
      aria-label={STATE_ORDER.map((s) => `${STATE_LABEL[s]} ${states[s] ?? 0}`).join(", ")}>
      {STATE_ORDER.map((s) => (states[s] ?? 0) > 0 && (
        <div key={s} title={`${STATE_LABEL[s]}: ${states[s]}`} className="mono flex items-center justify-center text-[9.5px] font-bold text-white overflow-hidden"
          style={{ width: `${((states[s] ?? 0) / total) * 100}%`, background: stateCss(s) }}>
          {(states[s] ?? 0) / total > 0.07 ? states[s] : ""}
        </div>
      ))}
    </div>
  );
}

const SHORT_LABEL: Record<string, string> = { MC: "Serviceable", NMCS: "Awaiting spares", NMCM_S: "In servicing", NMCM_U: "Rectification", DEPOT: "At depot (BRD)", WAIT: "Awaiting bay" };

export function StateLegend({ short = false }: { short?: boolean }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {STATE_ORDER.map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5 text-[11.5px] ink-2 whitespace-nowrap">
          <Code state={s} />{short ? SHORT_LABEL[s] : STATE_LABEL[s]}
        </span>
      ))}
    </div>
  );
}

/** Thin hairline meter (no rounded ends). */
export function Meter({ value, color = "var(--ink-2)", width }: { value: number; color?: string; width?: number }) {
  return (
    <div className="h-[5px]" style={{ background: "var(--rule-2)", width: width ?? "100%" }}>
      <div className="h-[5px]" style={{ width: `${Math.max(1, Math.min(100, value * 100))}%`, background: color }} />
    </div>
  );
}

export function Kv({ k, v, big }: { k: string; v: ReactNode; big?: boolean }) {
  return (
    <div>
      <div className="cond text-[11.5px] ink-3">{k}</div>
      <div className={`mono font-semibold ${big ? "text-[22px] leading-tight" : "text-[14px]"}`}>{v}</div>
    </div>
  );
}

export function Loading({ label = "RECEIVING" }: { label?: string }) {
  return <div className="mono text-[12px] ink-3 p-6">{label} <span className="caret" /></div>;
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="panel pad mono text-[12px]" style={{ color: "var(--crit)" }}>NO CONTACT — {error}</div>;
}

export function Note({ children }: { children: ReactNode }) {
  return <div className="foot mt-2">{children}</div>;
}
