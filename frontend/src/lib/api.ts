import { useEffect, useState } from "react";

/* ---------- session token (per tab; cleared on sign-out or a 401) ---------- */
const KEY = "tatpar-token";
let token: string | null = (() => {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
})();
let onUnauthorized: () => void = () => {};

export function setToken(t: string | null) {
  token = t;
  try {
    if (t) sessionStorage.setItem(KEY, t);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: token lives in memory only */
  }
}
export const getToken = () => token;
export const setUnauthorizedHandler = (f: () => void) => (onUnauthorized = f);
export const authHeaders = (): Record<string, string> => (token ? { Authorization: `Bearer ${token}` } : {});

async function check(r: Response) {
  if (r.status === 401) {
    onUnauthorized();
    throw new Error("401 session expired — sign in again");
  }
  if (!r.ok) {
    let msg = await r.text();
    try {
      msg = JSON.parse(msg).detail ?? msg;
    } catch {
      /* not JSON */
    }
    throw new Error(`${r.status} ${msg}`);
  }
  return r.json();
}

export async function getJSON<T = any>(path: string): Promise<T> {
  return check(await fetch(path, { headers: authHeaders() }));
}

export async function postJSON<T = any>(path: string, body: unknown): Promise<T> {
  return check(await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body) }));
}

export async function postForm<T = any>(path: string, form: FormData): Promise<T> {
  return check(await fetch(path, { method: "POST", headers: authHeaders(), body: form }));
}

/** Fetch on mount; keeps the previous data while refetching (no layout jump). */
export function useApi<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setLoading(true);
    getJSON<T>(path)
      .then((d) => live && (setData(d), setError(null)))
      .catch((e) => live && setError(String(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  return { data, error, loading, setData };
}

export const fmtPct = (x: number | null | undefined, d = 0) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
export const fmt = (x: number | null | undefined, d = 0) =>
  x == null ? "—" : x.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
export const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
