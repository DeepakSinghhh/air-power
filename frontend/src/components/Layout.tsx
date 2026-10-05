import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useApi } from "../lib/api";
import { useTheme } from "../lib/theme";
import { InkDefs } from "./glyphs";

/** Who is at the desk. The code is what gets written into the decision ledger. */
export const PERSONAS = [
  { id: "STN CDR", title: "Station Commander", focus: ["/", "/planner", "/loss"] },
  { id: "SENGO", title: "Senior Engineering Officer", focus: ["/flow", "/aircraft", "/snags"] },
  { id: "LOG OFFR", title: "Logistics Officer", focus: ["/sustainment", "/planner"] },
  { id: "DEPOT MGR", title: "Depot Manager", focus: ["/sustainment"] },
  { id: "AUDITOR", title: "Analyst / Auditor", focus: ["/proof"] },
];
const PersonaCtx = createContext<{ persona: string; setPersona: (p: string) => void }>({ persona: "STN CDR", setPersona: () => {} });
export const usePersona = () => useContext(PersonaCtx);

export const BOARDS = [
  { to: "/", no: "01", label: "STATE" },
  { to: "/planner", no: "02", label: "PLANNING CELL" },
  { to: "/flow", no: "03", label: "FLIGHT LINE" },
  { to: "/aircraft", no: "04", label: "AIRFRAME" },
  { to: "/sustainment", no: "05", label: "STORES" },
  { to: "/loss", no: "06", label: "AFTER-ACTION" },
  { to: "/snags", no: "07", label: "TECH LOG" },
  { to: "/proof", no: "08", label: "PROOF" },
];

const MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const p2 = (n: number) => String(n).padStart(2, "0");
/** Military date-time group, e.g. 051432Z OCT 26. */
export const dtg = (d: Date) => `${p2(d.getUTCDate())}${p2(d.getUTCHours())}${p2(d.getUTCMinutes())}Z ${MON[d.getUTCMonth()]} ${p2(d.getUTCFullYear() % 100)}`;
/** Data date (YYYY-MM-DD) as a DTG at the 0700Z state parade. */
export const dataDtg = (iso: string) => dtg(new Date(`${iso.slice(0, 10)}T07:00:00Z`));

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function Layout({ children, onCopilot }: { children: ReactNode; onCopilot: () => void }) {
  const [persona, setPersona] = useState(() => {
    try {
      const p = localStorage.getItem("tatpar-persona");
      return PERSONAS.some((x) => x.id === p) ? (p as string) : "STN CDR";
    } catch {
      return "STN CDR";
    }
  });
  const { dark, setMode } = useTheme();
  const meta = useApi<any>("/api/meta");
  const now = useClock();
  const ist = new Date(now.getTime() + 330 * 60000);
  const focus = PERSONAS.find((p) => p.id === persona)?.focus ?? [];
  const choose = (p: string) => {
    setPersona(p);
    try {
      localStorage.setItem("tatpar-persona", p);
    } catch {
      /* ignore */
    }
  };
  const m = meta.data;
  const nTails = m ? m.squadrons.reduce((a: number, s: any) => a + (s.n ?? s.tails ?? 16), 0) : 64;
  return (
    <PersonaCtx.Provider value={{ persona, setPersona: choose }}>
      <InkDefs />
      <div className="sticky top-0 z-20">
        <header className="strip">
          <Link to="/" className="brand"><b>TATPAR</b><span>तत्पर</span></Link>
          <nav className="tabs" aria-label="Boards">
            {BOARDS.map((b) => (
              <NavLink key={b.to} to={b.to} end={b.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
                <em>{b.no}</em>{b.label}
                {focus.includes(b.to) && <i className="focus" title={`Key board for ${persona}`} />}
              </NavLink>
            ))}
          </nav>
          <div className="dtg hidden lg:flex" title="Live date-time group (UTC)">
            {dtg(now)}<small>DTG · IST {p2(ist.getUTCHours())}{p2(ist.getUTCMinutes())}</small>
          </div>
          <label className="idtag hidden sm:block" title={PERSONAS.find((p) => p.id === persona)?.title}>
            <small>AUTHORITY</small>
            <select value={persona} onChange={(e) => choose(e.target.value)} aria-label="Persona">
              {PERSONAS.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
            </select>
          </label>
          <div className="sw" role="group" aria-label="Theme">
            <button className={dark ? "" : "on"} onClick={() => setMode("light")}>DAY</button>
            <button className={dark ? "on" : ""} onClick={() => setMode("dark")}>NIGHT</button>
          </div>
          <button className="duty" onClick={onCopilot} title="Ask the duty officer (offline copilot)">DUTY OFFR</button>
        </header>
        <div className="ribbon">
          <b>● NOTIONAL DATA — NOT IAF</b>
          <span>STATE AS AT {m ? dataDtg(m.today) : "…"}</span>
          <span>FLEET {nTails} AC · {m?.squadrons?.length ?? 4} SQN · {m ? Object.keys(m.types).length : 2} TYPES · {m?.bases?.length ?? 5} BASES</span>
          <span>HUMS: NASA C-MAPSS · DUST: CAMS 2024 · LOGBOOK NLP: MAINTNET</span>
        </div>
      </div>
      <main className="px-3 sm:px-5 py-4">{children}</main>
    </PersonaCtx.Provider>
  );
}
