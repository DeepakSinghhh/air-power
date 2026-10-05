import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getJSON, getToken, setToken, setUnauthorizedHandler } from "./api";

export type User = { id: string; name: string; role: string; title: string; permissions: string[] };

type Auth = {
  user: User | null;
  ready: boolean;
  login: (id: string, pin: string) => Promise<void>;
  logout: () => void;
  can: (perm: string) => boolean;
};
const Ctx = createContext<Auth>({ user: null, ready: false, login: async () => {}, logout: () => {}, can: () => false });
export const useAuth = () => useContext(Ctx);

/** Holds the signed-in user. The server is the authority: every request carries the token and
 *  every decision is re-checked there; `can()` only decides what the UI offers. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);
  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!getToken()) {
      setReady(true);
      return;
    }
    getJSON<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, [logout]);
  const login = useCallback(async (id: string, pin: string) => {
    const res = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, pin }) });
    const r = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(String(r.detail ?? `sign-in failed (${res.status})`).toUpperCase());
    setToken(r.token);
    setUser(r.user);
  }, []);
  const value = useMemo<Auth>(() => ({ user, ready, login, logout, can: (p) => !!user?.permissions.includes(p) }), [user, ready, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
