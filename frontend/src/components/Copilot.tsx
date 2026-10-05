import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { postJSON } from "../lib/api";
import { dtg } from "./Layout";

type Msg = { role: "q" | "a"; text: string; at: string; links?: { label: string; to: string }[]; table?: any[]; engine?: string };

const SUGGEST = [
  "How many aircraft will Sqn A have in 2 weeks?",
  "Which squadron has the lowest readiness?",
  "Which tails are most likely to snag this week?",
  "Status of HF-114",
  "Which spares should we move?",
  "Why is readiness low?",
  "Engines closest to removal",
];

/** Duty officer: the offline copilot as a teleprinter log. Every answer cites the board it came from. */
export function Copilot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "a", at: dtg(new Date()), text: "DUTY OFFICER ON WATCH. ASK ABOUT READINESS, A TAIL, SPARES OR SNAGS. ANSWERS COME FROM TATPAR'S OWN MODELS AND RECORDS. NO NETWORK USED." },
  ]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, busy]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const ask = async (text: string) => {
    if (!text.trim()) return;
    setMsgs((m) => [...m, { role: "q", text: text.toUpperCase(), at: dtg(new Date()) }]);
    setQ("");
    setBusy(true);
    try {
      const r = await postJSON<any>("/api/copilot", { question: text });
      setMsgs((m) => [...m, { role: "a", at: dtg(new Date()), text: r.answer, links: r.links, table: r.table, engine: r.engine }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "a", at: dtg(new Date()), text: `NO CONTACT — ${e}` }]);
    } finally {
      setBusy(false);
    }
  };
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "var(--shade)" }} onClick={onClose}>
      <aside className="h-full w-full max-w-[500px] flex flex-col" style={{ background: "var(--panel)", borderLeft: "2px solid var(--ink)" }}
        onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Duty officer">
        <div className="lp"><span>DUTY OFFICER · TELEPRINTER</span><span className="meta"><button onClick={onClose} aria-label="Close">CLOSE ✕</button></span></div>
        <div className="flex-1 overflow-y-auto tp px-4 py-3">
          {msgs.map((m, i) => (
            <div key={i} className="mb-3">
              <div className="text-[10.5px] ink-3">{m.at} · {m.role === "q" ? "FROM DESK" : "FROM DUTY OFFR"}</div>
              <div style={{ whiteSpace: "pre-wrap", color: m.role === "q" ? "var(--blue-ink)" : "var(--ink)", fontWeight: m.role === "q" ? 600 : 400 }}>
                {m.role === "q" ? "> " : ""}{m.text}
              </div>
              {m.table && m.table.length > 0 && (
                <table className="ledger mt-1" style={{ background: "transparent" }}><thead><tr>{Object.keys(m.table[0]).map((k) => <th key={k} style={{ background: "var(--paper)" }}>{k}</th>)}</tr></thead>
                  <tbody>{m.table.map((r, j) => <tr key={j}>{Object.values(r).map((v: any, k) => <td key={k} className="m">{String(v)}</td>)}</tr>)}</tbody></table>
              )}
              {m.links && <div className="flex flex-wrap gap-2 mt-1">{m.links.map((l) => <Link key={l.to} to={l.to} onClick={onClose} className="tag">{l.label.toUpperCase()} →</Link>)}</div>}
              {m.engine && <div className="text-[10px] ink-3 mt-0.5">SRC: {m.engine.toUpperCase()}</div>}
            </div>
          ))}
          {busy && <div className="ink-3">RECEIVING <span className="caret" /></div>}
          <div ref={end} />
        </div>
        <div className="px-4 py-2 flex flex-wrap gap-1.5 border-t" style={{ borderColor: "var(--rule)" }}>
          {SUGGEST.map((s) => <button key={s} className="tag" onClick={() => ask(s)}>{s}</button>)}
        </div>
        <form className="flex gap-2 p-3 border-t" style={{ borderColor: "var(--rule)" }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <span className="mono self-center ink-3">&gt;</span>
          <input className="input flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a question, e.g. status of HF-202" autoFocus />
          <button className="btn ink" disabled={busy}>SEND</button>
        </form>
      </aside>
    </div>
  );
}
