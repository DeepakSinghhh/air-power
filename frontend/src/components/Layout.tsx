import {
  Activity, BarChart3, Boxes, Database, Gauge, MessageSquareText, Moon, Plane, ShieldCheck, Sun, Target, Waypoints, Wrench,
} from "lucide-react";
import { createContext, useContext, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useApi } from "../lib/api";
import { useTheme } from "../lib/theme";

export const PERSONAS = [
  { id: "Commander", focus: ["/", "/planner", "/loss"] },
  { id: "Squadron Engineering Officer", focus: ["/flow", "/aircraft", "/snags"] },
  { id: "Logistics Officer", focus: ["/sustainment", "/planner"] },
  { id: "Depot Manager", focus: ["/sustainment"] },
  { id: "Analyst / Auditor", focus: ["/data", "/models"] },
];
const PersonaCtx = createContext<{ persona: string; setPersona: (p: string) => void }>({ persona: "Commander", setPersona: () => {} });
export const usePersona = () => useContext(PersonaCtx);

const NAV = [
  { to: "/", label: "Command overview", icon: Gauge },
  { to: "/planner", label: "Readiness planner", icon: Target },
  { to: "/flow", label: "Fleet flow & plan", icon: Waypoints },
  { to: "/aircraft", label: "Aircraft health", icon: Plane },
  { to: "/sustainment", label: "Sustainment", icon: Boxes },
  { to: "/loss", label: "Readiness loss", icon: BarChart3 },
  { to: "/snags", label: "Snag intelligence", icon: Wrench },
  { to: "/data", label: "Data fabric", icon: Database },
  { to: "/models", label: "Models & trust", icon: ShieldCheck },
];

export function Layout({ children, onCopilot }: { children: ReactNode; onCopilot: () => void }) {
  const [persona, setPersona] = useState(() => {
    try {
      return localStorage.getItem("tatpar-persona") || "Commander";
    } catch {
      return "Commander";
    }
  });
  const { mode, setMode, dark } = useTheme();
  const meta = useApi<any>("/api/meta");
  const focus = PERSONAS.find((p) => p.id === persona)?.focus ?? [];
  const choose = (p: string) => {
    setPersona(p);
    try {
      localStorage.setItem("tatpar-persona", p);
    } catch {
      /* ignore */
    }
  };
  return (
    <PersonaCtx.Provider value={{ persona, setPersona: choose }}>
      <div className="flex min-h-full">
        <div className="hidden md:block w-[232px] flex-none" style={{ background: "var(--nav)" }}>
        <aside className="flex flex-col sticky top-0 h-screen" style={{ color: "var(--nav-ink)" }}>
          <div className="px-5 pt-5 pb-4">
            <div className="flex items-center gap-2">
              <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="7" fill="#13294a" /><path d="M16 5 L19 14 L28 17 L19 19 L16 27 L13 19 L4 17 L13 14 Z" fill="#E8871E" /></svg>
              <div>
                <div className="font-bold tracking-wide text-white">TATPAR</div>
                <div className="text-[11px] opacity-75">तत्पर · readiness assurance</div>
              </div>
            </div>
          </div>
          <nav className="flex-1 px-2 space-y-0.5">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={to === "/"}
                className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] no-underline ${isActive ? "font-semibold" : ""}`}
                style={({ isActive }) => ({ background: isActive ? "rgba(232,135,30,0.16)" : "transparent", color: isActive ? "#fff" : "var(--nav-ink)" })}>
                <Icon size={16} />
                <span className="flex-1">{label}</span>
                {focus.includes(to) && <span className="dot" style={{ background: "var(--brand)" }} title={`Key view for ${persona}`} />}
              </NavLink>
            ))}
          </nav>
          <button onClick={onCopilot} className="mx-3 mb-3 btn justify-center" style={{ background: "rgba(255,255,255,0.08)", color: "#fff", borderColor: "rgba(255,255,255,0.15)" }}>
            <MessageSquareText size={15} /> Ask TATPAR
          </button>
          <div className="px-5 pb-4 text-[11px] opacity-70 leading-snug">
            Notional fleet · public & synthetic data only. Not IAF data.
          </div>
        </aside>
        </div>
        <div className="flex-1 min-w-0 flex flex-col">
          <header className="sticky top-0 z-10 flex flex-wrap items-center gap-3 px-4 md:px-6 py-3 border-b" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
            <Activity size={16} style={{ color: "var(--brand)" }} />
            <span className="text-[13px] secondary">
              Today <b className="tabular" style={{ color: "var(--text-primary)" }}>{meta.data?.today ?? "…"}</b>
            </span>
            <span className="chip"><span className="dot" style={{ background: "var(--warning)" }} />NOTIONAL DATA</span>
            <div className="flex-1" />
            <label className="text-[12px] secondary flex items-center gap-2">
              Persona
              <select className="input" value={persona} onChange={(e) => choose(e.target.value)}>
                {PERSONAS.map((p) => <option key={p.id}>{p.id}</option>)}
              </select>
            </label>
            <button className="btn" aria-label="Toggle theme" onClick={() => setMode(dark ? "light" : "dark")} title={`Theme: ${mode}`}>
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </button>
            <button className="btn md:hidden" onClick={onCopilot}><MessageSquareText size={15} /></button>
          </header>
          <nav className="md:hidden flex gap-1 overflow-x-auto px-3 py-2 border-b" style={{ borderColor: "var(--border)" }}>
            {NAV.map(({ to, label }) => (
              <NavLink key={to} to={to} end={to === "/"} className="chip no-underline">{label}</NavLink>
            ))}
          </nav>
          <main className="flex-1 px-4 md:px-6 py-5">{children}</main>
        </div>
      </div>
    </PersonaCtx.Provider>
  );
}
