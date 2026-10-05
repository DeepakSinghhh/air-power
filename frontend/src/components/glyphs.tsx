import type { ReactNode } from "react";

/** Shared SVG defs: the rubber-stamp ink texture. Rendered once by the shell. */
export function InkDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
      <filter id="ink">
        <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="5" />
        <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -0.9 1.2" />
        <feComposite in="SourceGraphic" operator="in" />
      </filter>
    </svg>
  );
}

/** Delta-wing token used on the phase track (nose points right, toward the hangar). */
export function Jet({ x, y, size = 15, color = "var(--ink)", title }: { x: number; y: number; size?: number; color?: string; title?: string }) {
  const s = size / 20;
  return (
    <g className="jet" style={{ transform: `translate(${x}px, ${y}px)` }}>
      {title && <title>{title}</title>}
      <path transform={`scale(${-s},${s})`} fill={color}
        d="M-10 0 L-2 -2 L4 -9 L6 -9 L3 -2 L8 -1.5 L10 -5 L11 -5 L10 0 L11 5 L10 5 L8 1.5 L3 2 L6 9 L4 9 L-2 2 Z" />
    </g>
  );
}

export function Hangar({ x, y, h = 100, label = "BAY" }: { x: number; y: number; h?: number; label?: string }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <path d={`M0 ${h} L0 22 L20 6 L40 22 L40 ${h}`} fill="var(--inset)" stroke="var(--ink)" strokeWidth="2" />
      <text x="20" y={h / 2 + 6} textAnchor="middle" className="mono" fontSize="9.5" fill="var(--ink-3)">{label}</text>
    </g>
  );
}

export type StampTone = "red" | "green" | "blue" | "violet" | "grey";
export function Stamp({ tone, children, sub, rotate = -2, className = "" }: { tone: StampTone; children: ReactNode; sub?: string; rotate?: number; className?: string }) {
  return (
    <span className={`stamp ${tone} ${className}`} style={{ transform: `rotate(${rotate}deg)` }}>
      {children}{sub && <small>{sub}</small>}
    </span>
  );
}

const STATE_STAMP: Record<string, [string, StampTone, string?]> = {
  MC: ["SERVICEABLE", "green"], NMCS: ["U/S", "red", "SPARES"], NMCM_U: ["U/S", "red", "RECT"],
  NMCM_S: ["IN SVC", "blue", "SCHED"], DEPOT: ["AT BRD", "violet"], WAIT: ["AWAIT BAY", "grey"],
};
/** Deterministic small rotation so a column of stamps looks hand-applied but never jitters between renders. */
export function StateStamp({ state, seed = "" }: { state: string; seed?: string }) {
  const [w, tone, sub] = STATE_STAMP[state] ?? [state, "grey"];
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) % 997;
  return <Stamp tone={tone} sub={sub} rotate={(h % 70) / 10 - 3.5}>{w}</Stamp>;
}

/* ---------- whiteprint planform (notional twin-engine fighter, nose up, 400 x 540 units) ---------- */
const R: [number, number][] = [[200, 22], [207, 56], [213, 100], [219, 150], [224, 172], [272, 196], [273, 207], [227, 204], [236, 228], [250, 254],
  [362, 362], [364, 392], [300, 398], [262, 394], [262, 436], [330, 474], [331, 490], [268, 487], [262, 500], [252, 514],
  [236, 514], [231, 500], [212, 494], [200, 490]];
const OUTLINE = "M" + [...R, ...R.slice(0, -1).reverse().map(([x, y]) => [400 - x, y] as [number, number])].map(([x, y]) => `${x} ${y}`).join(" L") + " Z";

export type Balloon = { n: number; x: number; y: number; bx: number; by: number; hot?: boolean; title?: string };

/** Engineering-drawing planform with numbered item balloons and leader lines. */
export function Planform({ balloons, highlight, width = 440 }: { balloons: Balloon[]; highlight?: { x: number; y: number }; width?: number }) {
  const S = 0.6, TX = 100, TY = 8;
  const F = (x: number, y: number) => [TX + S * x, TY + S * y];
  const h = (width / 440) * 330;
  return (
    <svg width="100%" viewBox="0 0 440 330" style={{ maxWidth: width, height: "auto", maxHeight: h }} role="img" aria-label="Aircraft planform with numbered condition callouts">
      <g transform={`translate(${TX},${TY}) scale(${S})`} fill="none" stroke="var(--blue-ink)">
        <path d={OUTLINE} strokeWidth="2.4" />
        <ellipse cx="200" cy="118" rx="8" ry="30" strokeWidth="1.6" />
        <path d="M200 22 L200 490" strokeWidth="1" strokeDasharray="14 4 2 4" />
        <rect x="220" y="300" width="34" height="210" strokeWidth="1.4" strokeDasharray="5 3" />
        <rect x="146" y="300" width="34" height="210" strokeWidth="1.4" strokeDasharray="5 3" />
        <line x1="242" y1="404" x2="246" y2="476" strokeWidth="4" />
        <line x1="158" y1="404" x2="154" y2="476" strokeWidth="4" />
        <path d="M226 172 L224 228 M174 172 L176 228" strokeWidth="1.2" strokeDasharray="5 3" />
      </g>
      {highlight && (() => { const [cx, cy] = F(highlight.x, highlight.y); return <circle cx={cx} cy={cy} r="22" fill="none" stroke="var(--stamp-red)" strokeWidth="1.5" strokeDasharray="4 3" />; })()}
      {balloons.map((b) => {
        const [px, py] = F(b.x, b.y);
        const col = b.hot ? "var(--stamp-red)" : "var(--blue-ink)";
        const ex = b.bx > 220 ? b.bx - 13 : b.bx + 13;
        return (
          <g key={b.n}>
            {b.title && <title>{b.title}</title>}
            <circle cx={px} cy={py} r="2.6" fill={col} />
            <line x1={px} y1={py} x2={ex} y2={b.by} stroke={col} strokeWidth=".9" />
            <circle cx={b.bx} cy={b.by} r="13" fill="var(--whiteprint)" stroke={col} strokeWidth="1.4" />
            <text x={b.bx} y={b.by + 4.5} textAnchor="middle" fontFamily="IBM Plex Mono" fontWeight="700" fontSize="12" fill={col}>{b.n}</text>
          </g>
        );
      })}
    </svg>
  );
}
