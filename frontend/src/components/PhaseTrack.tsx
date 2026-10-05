import { Hangar, Jet } from "./glyphs";

export type LadderRow = { tail: string; residual_fh: number; ideal_fh?: number; in_check: string; interval_fh: number };
export type Lane = { label: string; rows: LadderRow[]; ideal?: boolean };

/** Phase track: each aircraft is a token placed by flight hours left before its phase check; the hangar
 *  (one bay) is on the right. Tokens bunching near the gate is the readiness wave forming. Tokens are keyed
 *  by tail, so switching a lane's data slides them (CSS transition on .jet). */
export function PhaseTrack({ lanes, interval = 200, laneH = 40, W = 900 }: { lanes: Lane[]; interval?: number; laneH?: number; W?: number }) {
  const x0 = 150, x1 = W - 100, top = 20;
  const H = top + lanes.length * laneH + 26;
  const X = (fh: number) => x0 + (interval - Math.max(0, Math.min(interval, fh))) / interval * (x1 - x0);
  const ticks = [interval, interval * 0.75, interval / 2, interval / 4, 0];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Phase track: aircraft positioned by flight hours to phase check">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={X(v)} x2={X(v)} y1={top - 4} y2={H - 22} stroke="var(--grid)" />
          <text x={X(v)} y={H - 8} textAnchor="middle" className="mono" fontSize="10" fill="var(--ink-3)">{Math.round(v)}</text>
        </g>
      ))}
      <text x={x0} y={11} className="mono" fontSize="10" fill="var(--ink-3)">← FH REMAINING TO PHASE CHECK</text>
      <text x={x1} y={11} textAnchor="end" className="mono" fontSize="10" fill="var(--ink-3)">DUE →</text>
      <Hangar x={x1 + 22} y={top - 6} h={lanes.length * laneH + 4} label="BAY" />
      {lanes.map((ln, i) => {
        const y = top + i * laneH + laneH / 2;
        return (
          <g key={ln.label}>
            <text x={0} y={y + 4} className="cond" fontSize="13" fontWeight="600" fill="var(--ink-2)">{ln.label}</text>
            <line x1={x0} x2={x1} y1={y} y2={y} className="trk" />
            {ln.ideal && ln.rows.filter((r) => r.ideal_fh != null).map((r) => (
              <line key={`i-${r.tail}`} x1={X(r.ideal_fh!)} x2={X(r.ideal_fh!)} y1={y + 9} y2={y + 15} stroke="var(--accent)" strokeWidth="2" />
            ))}
            {[...ln.rows].sort((a, b) => a.tail.localeCompare(b.tail)).map((r) => (
              <Jet key={r.tail} x={r.in_check ? x1 + 42 : X(r.residual_fh)} y={y} size={15}
                color={r.in_check ? "var(--s-nmcms)" : "var(--ink)"}
                title={`${r.tail}: ${r.in_check ? `in ${r.in_check} check` : `${Math.round(r.residual_fh)} FH to phase`}`} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}
