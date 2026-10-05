import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Tokens = Record<string, string>;
const NAMES = [
  "surface-1", "surface-2", "page", "text-primary", "text-secondary", "text-muted", "grid", "axis",
  "series-1", "series-2", "series-3", "series-4", "series-5", "series-6", "series-7", "series-8", "baseline",
  "good", "warning", "serious", "critical", "brand",
];

function read(): Tokens {
  const cs = getComputedStyle(document.documentElement);
  const t: Tokens = {};
  for (const n of NAMES) t[n] = cs.getPropertyValue(`--${n}`).trim();
  return t;
}

type Mode = "light" | "dark" | "system";
const Ctx = createContext<{ tokens: Tokens; mode: Mode; setMode: (m: Mode) => void; dark: boolean }>({
  tokens: {}, mode: "system", setMode: () => {}, dark: false,
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => {
    try {
      return (localStorage.getItem("tatpar-theme") as Mode) || "system";
    } catch {
      return "system";
    }
  });
  const [tokens, setTokens] = useState<Tokens>({});
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", mode);
    try {
      localStorage.setItem("tatpar-theme", mode);
    } catch {
      /* storage unavailable */
    }
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => {
      setTokens(read());
      setDark(mode === "dark" || (mode === "system" && mq.matches));
    };
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [mode]);
  const value = useMemo(() => ({ tokens, mode, setMode, dark }), [tokens, mode, dark]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

export const STATE_ORDER = ["MC", "NMCS", "NMCM_U", "NMCM_S", "DEPOT", "WAIT"] as const;
export const STATE_LABEL: Record<string, string> = {
  MC: "Mission capable",
  NMCS: "Awaiting spares",
  NMCM_U: "Unscheduled maint.",
  NMCM_S: "Scheduled maint.",
  DEPOT: "Depot overhaul",
  WAIT: "Awaiting bay",
};
export const stateColor = (t: Tokens, s: string) =>
  ({ MC: t["series-1"], NMCS: t["series-2"], NMCM_U: t["series-3"], NMCM_S: t["series-4"], DEPOT: t["series-5"], WAIT: t["series-7"] })[s] ||
  t["baseline"];
export const SQN_COLOR = (t: Tokens, i: number) => t[`series-${[1, 2, 3, 4][i] ?? 8}`];
