import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { InkDefs } from "./glyphs";

type RosterUser = { id: string; name: string; role: string; demo_pin?: string };

/** Sign-in: pick the authority at the desk, enter the PIN. Demo PINs are shown only for the notional roster. */
export function Login() {
  const { login } = useAuth();
  const [roster, setRoster] = useState<{ users: RosterUser[]; demo: boolean } | null>(null);
  const [id, setId] = useState("stncdr");
  const [pin, setPin] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    fetch("/api/auth/roster").then((r) => r.json()).then((r) => {
      setRoster(r);
      if (r.users?.length && !r.users.some((u: RosterUser) => u.id === "stncdr")) setId(r.users[0].id);
    }).catch(() => setErr("NO CONTACT WITH SERVER"));
  }, []);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(id, pin);
    } catch (x: any) {
      setErr(String(x.message ?? x));
      setPin("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="min-h-screen flex flex-col">
      <InkDefs />
      <header className="strip"><span className="brand"><b>TATPAR</b><span>तत्पर</span></span><span className="flex-1" /></header>
      <div className="ribbon"><b>● NOTIONAL DATA — NOT IAF</b><span>READINESS ASSURANCE FOR AIR FLEETS · SIH 2026 · PS 26249</span></div>
      <main className="flex-1 flex items-start justify-center px-4 py-10">
        <form onSubmit={submit} className="panel w-full max-w-[560px]" aria-label="Sign in">
          <div className="lp"><span>Authentication</span><span className="meta">EVERY DECISION IS SIGNED WITH YOUR IDENTITY</span></div>
          <div className="pad space-y-4">
            <div>
              <div className="cond text-[13px] ink-3 mb-1.5">AUTHORITY</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5" role="radiogroup">
                {(roster?.users ?? []).map((u) => (
                  <button type="button" key={u.id} role="radio" aria-checked={id === u.id} onClick={() => setId(u.id)}
                    className="text-left px-3 py-2 border" style={{ borderColor: id === u.id ? "var(--ink)" : "var(--rule)", background: id === u.id ? "var(--ink)" : "var(--panel)", color: id === u.id ? "var(--panel)" : "var(--ink)" }}>
                    <div className="mono font-semibold text-[13px]">{u.role}</div>
                    <div className="text-[11.5px]" style={{ opacity: 0.75 }}>{u.name}</div>
                  </button>
                ))}
              </div>
            </div>
            <label className="block">
              <div className="cond text-[13px] ink-3 mb-1.5">PIN</div>
              <input className="input w-full text-[18px] tracking-[.4em]" type="password" inputMode="numeric" autoComplete="current-password" value={pin}
                onChange={(e) => setPin(e.target.value)} autoFocus aria-label="PIN" />
            </label>
            {err && <div className="mono text-[12px]" style={{ color: "var(--crit)" }}>✕ {err}</div>}
            <button className="btn ink w-full justify-center !py-2 !text-[16px]" disabled={busy || !pin}>{busy ? "VERIFYING…" : "SIGN IN"}</button>
            {roster?.demo && (
              <div className="foot border-t pt-2" style={{ borderColor: "var(--rule)" }}>
                PROTOTYPE ROSTER (NOTIONAL USERS) — DEMO PINS: {roster.users.map((u) => `${u.role} ${u.demo_pin}`).join(" · ")}.
                A unit deployment loads its own roster (TATPAR_USERS) and these PINs stop working.
              </div>
            )}
          </div>
        </form>
      </main>
    </div>
  );
}
