import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Tokens = Record<string, string>;
const NAMES = [
  "page", "panel", "inset", "paper", "rule", "rule-2", "ink", "ink-2", "ink-3", "plate", "accent", "alert", "blue-ink",
  "grid", "axis", "s-mc", "s-nmcs", "s-nmcms", "s-nmcmu", "s-depot", "s-wait", "cur", "tat",
  "sq-1", "sq-2", "sq-3", "sq-4", "good", "warn", "crit", "stamp-red",
];

function read(): Tokens {
  const cs = getComputedStyle(document.documentElement);
  const t: Tokens = {};
  for (const n of NAMES) t[n] = cs.getPropertyValue(`--${n}`).trim();
  return t;
}

type Mode = "light" | "dark";
const Ctx = createContext<{ tokens: Tokens; mode: Mode; setMode: (m: Mode) => void; dark: boolean }>({
  tokens: {}, mode: "light", setMode: () => {}, dark: false,
});

/** Day (paper) is the default; night is one click away and remembered per browser. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => {
    try {
      return localStorage.getItem("tatpar-theme") === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });
  const [tokens, setTokens] = useState<Tokens>({});
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", mode);
    try {
      localStorage.setItem("tatpar-theme", mode);
    } catch {
      /* storage unavailable */
    }
    setTokens(read());
  }, [mode]);
  const value = useMemo(() => ({ tokens, mode, setMode, dark: mode === "dark" }), [tokens, mode]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

/** Board order: serviceable first, then the four reasons an aircraft is down, then the bay queue. */
export const STATE_ORDER = ["MC", "NMCS", "NMCM_S", "NMCM_U", "DEPOT", "WAIT"] as const;
export const STATE_CODE: Record<string, string> = { MC: "S", NMCS: "SPR", NMCM_U: "U/S", NMCM_S: "SVC", DEPOT: "DEP", WAIT: "BAY" };
export const STATE_LABEL: Record<string, string> = {
  MC: "Serviceable",
  NMCS: "U/S awaiting spares",
  NMCM_U: "U/S rectification",
  NMCM_S: "In servicing",
  DEPOT: "At depot (BRD)",
  WAIT: "Awaiting bay",
};
export const STATE_VAR: Record<string, string> = {
  MC: "s-mc", NMCS: "s-nmcs", NMCM_U: "s-nmcmu", NMCM_S: "s-nmcms", DEPOT: "s-depot", WAIT: "s-wait",
};
export const stateColor = (t: Tokens, s: string) => t[STATE_VAR[s]] || t["ink-3"];
export const stateCss = (s: string) => `var(--${STATE_VAR[s] ?? "ink-3"})`;
export const SQN_COLOR = (t: Tokens, i: number) => t[`sq-${i + 1}`] ?? t["ink-2"];
