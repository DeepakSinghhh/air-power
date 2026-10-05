import { Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { postJSON } from "../lib/api";

type Msg = { role: "user" | "assistant"; text: string; links?: { label: string; to: string }[]; table?: any[]; engine?: string };

const SUGGEST = [
  "How many aircraft will Sqn A have in 2 weeks?",
  "Which tails are most likely to snag this week?",
  "Status of HF-114",
  "Which spares should we move?",
  "Why is readiness low?",
  "Engines closest to removal",
];

export function Copilot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "assistant", text: "Ask about readiness, aircraft, spares or snags. I answer from TATPAR's own models and records and cite them. I run fully offline." },
  ]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs]);
  const ask = async (text: string) => {
    if (!text.trim()) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setQ("");
    setBusy(true);
    try {
      const r = await postJSON<any>("/api/copilot", { question: text });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, links: r.links, table: r.table, engine: r.engine }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `Sorry — ${e}` }]);
    } finally {
      setBusy(false);
    }
  };
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "rgba(0,0,0,0.25)" }} onClick={onClose}>
      <aside className="h-full w-full max-w-[460px] flex flex-col" style={{ background: "var(--surface-1)", borderLeft: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
          <div><div className="h-title">Ask TATPAR</div><div className="h-sub">Offline copilot · answers cite platform data</div></div>
          <button className="btn" onClick={onClose} aria-label="Close"><X size={15} /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {msgs.map((m, i) => (
            <div key={i} className={`rounded-xl px-3 py-2 text-[13px] ${m.role === "user" ? "ml-10" : "mr-4"}`}
              style={{ background: m.role === "user" ? "rgba(232,135,30,0.14)" : "var(--surface-2)" }}>
              <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
              {m.table && m.table.length > 0 && (
                <table className="tbl mt-2"><thead><tr>{Object.keys(m.table[0]).map((k) => <th key={k}>{k}</th>)}</tr></thead>
                  <tbody>{m.table.map((r, j) => <tr key={j}>{Object.values(r).map((v: any, k) => <td key={k} className="tabular">{String(v)}</td>)}</tr>)}</tbody></table>
              )}
              {m.links && <div className="flex flex-wrap gap-2 mt-2">{m.links.map((l) => <Link key={l.to} to={l.to} onClick={onClose} className="chip no-underline">{l.label} →</Link>)}</div>}
              {m.engine && <div className="muted text-[10.5px] mt-1">{m.engine}</div>}
            </div>
          ))}
          {busy && <div className="muted text-[12px]">Thinking…</div>}
          <div ref={end} />
        </div>
        <div className="px-4 pb-2 flex flex-wrap gap-1.5">
          {SUGGEST.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}
        </div>
        <form className="flex gap-2 p-3 border-t" style={{ borderColor: "var(--border)" }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input className="input flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about readiness, a tail, spares…" />
          <button className="btn btn-primary" disabled={busy}><Send size={14} /></button>
        </form>
      </aside>
    </div>
  );
}
