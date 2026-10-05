import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Stamp } from "../components/glyphs";
import { dataDtg } from "../components/Layout";
import { Board, ErrorBox, Loading, Meter, Panel } from "../components/ui";
import { fmtPct, postJSON, useApi } from "../lib/api";
import { useAuth } from "../lib/auth";

const EXAMPLES: [string, string][] = [
  ["HYD PRESSURE LH SYSTEM MEIN FLUCTUATION, TAXI KE DAURAN", "HYD_PUMP"],
  ["HYD PR FLUCTUATING ON LH SYS DURING TAXI", "HYD_PUMP"],
  ["FCS CHANNEL 2 FAIL DURING TAKE OFF. FAULT CLEARED ON BITE RESET", ""],
  ["Radar TX fail in A2A mode, intermittent", "RADAR"],
  ["No 1 eng EGT margin low, thrust low on take off", ""],
  ["COMM 1 WEAK AND GARBLED", "VUHF"],
];

export default function SnagsPage() {
  const [text, setText] = useState(EXAMPLES[0][0]);
  const [tail, setTail] = useState("HF-101");
  const [lru, setLru] = useState(EXAMPLES[0][1]);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [filed, setFiled] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const { can } = useAuth();
  const meta = useApi<any>("/api/meta");
  const stats = useApi<any>("/api/snags/stats");
  const recent = useApi<any[]>("/api/snags/recent", [filed?.snag_id]);
  const fleet = useApi<any[]>("/api/fleet");
  const analyse = async (txt = text, l = lru, file = false) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await postJSON(file ? "/api/snags/file" : "/api/snags/analyse", { text: txt, tail, lru: l || null });
      setRes(r);
      setFiled(file ? r.entry : null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    analyse();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (stats.error) return <ErrorBox error={stats.error} />;
  const by = stats.data?.by_ata ?? [];
  const maxBy = Math.max(1, ...by.map((r: any) => r.snags));
  const today = meta.data?.today;
  return (
    <Board no="07" title="Tech log" sub="Write the snag the way it is written on the line — abbreviations and Hinglish welcome. TATPAR codes the ATA chapter, finds similar past cases (this fleet + real MaintNet logbooks), ranks what fixed it before, and flags likely No-Fault-Found removals before a spare is consumed.">
      <div className="f700">
        <div className="fh"><h3>New entry</h3><span>FORM 700 (NOTIONAL) · TATPAR CODES IT AS YOU FILE</span></div>
        <table>
          <thead><tr><th style={{ width: 92 }}>Date</th><th style={{ width: 110 }}>Tail</th><th>Defect reported</th><th style={{ width: 230 }}>Suspect LRU</th><th style={{ width: 150 }} /></tr></thead>
          <tbody><tr>
            <td className="n">{today ?? "—"}</td>
            <td><select className="input w-full" value={tail} onChange={(e) => setTail(e.target.value)} aria-label="Tail">{(fleet.data || []).map((f) => <option key={f.tail}>{f.tail}</option>)}</select></td>
            <td><textarea className="w-full min-h-[54px] bg-transparent outline-none resize-y" style={{ fontFamily: "Courier Prime, monospace", fontSize: 14, color: "var(--ink)", border: "none" }} value={text} onChange={(e) => setText(e.target.value)} aria-label="Defect text" /></td>
            <td><select className="input w-full" value={lru} onChange={(e) => setLru(e.target.value)} aria-label="Suspect LRU">
              <option value="">— not known —</option>
              {(meta.data?.lrus || []).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select></td>
            <td>{can("snags:file")
              ? <button className="btn ink w-full justify-center" onClick={() => analyse(text, lru, true)} disabled={busy}>{busy ? "CODING…" : "FILE ENTRY"}</button>
              : <button className="btn w-full justify-center" onClick={() => analyse()} disabled={busy}>{busy ? "CODING…" : "ANALYSE ONLY"}</button>}</td>
          </tr></tbody>
        </table>
        {filed && <div className="mt-2 flex items-center gap-3"><span className="stamp green thump" style={{ transform: "rotate(-3deg)" }}>FILED {filed.snag_id}</span>
          <span className="mono text-[11.5px] ink-2">ENTERED IN THE TECH LOG OF {filed.tail} BY {filed.filed_by} · CODED ATA {filed.ata}</span></div>}
        {!can("snags:file") && <div className="mono text-[11px] ink-3 mt-2">SIGNED IN AS A ROLE THAT CANNOT FILE — ANALYSIS ONLY (FILING: SENGO / STN CDR).</div>}
        {err && <div className="mono text-[11.5px] mt-2" style={{ color: "var(--crit)" }}>✕ {err}</div>}
        <div className="flex flex-wrap gap-1.5 mt-2 items-center"><span className="cond text-[12px] ink-3 mr-1">TRY (ANALYSE ONLY):</span>
          {EXAMPLES.slice(1).map(([e, l]) => <button key={e} className="tag" onClick={() => { setText(e); setLru(l); analyse(e, l); }}>{e.length > 38 ? e.slice(0, 38) + "…" : e}</button>)}
        </div>
      </div>

      {res && (
        <div className={`grid grid-cols-1 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)] gap-4 mt-4 ${busy ? "opacity-50" : ""}`}>
          <div className="space-y-4 min-w-0">
            <Panel title="ATA chapter" meta="TF-IDF + LOGISTIC REGRESSION">
              <div className="flex items-center gap-4">
                <span className="stamp big blue" style={{ transform: "rotate(-4deg)" }}><b>ATA {res.ata[0].ata}</b><span>{res.ata[0].name.toUpperCase()}</span></span>
                <div className="mono"><div className="text-[24px] font-bold">{fmtPct(res.ata[0].p)}</div><div className="text-[11px] ink-3">CONFIDENCE</div></div>
              </div>
              <div className="mt-3">{res.ata.slice(1).map((a: any) => <div key={a.ata} className="mono text-[11.5px] ink-2 flex justify-between border-b py-[2px]" style={{ borderColor: "var(--rule-2)" }}><span>ATA {a.ata} {a.name.toUpperCase()}</span><span>{fmtPct(a.p, 1)}</span></div>)}</div>
            </Panel>
            <Panel title="Removal decision" meta="NO-FAULT-FOUND MODEL">
              {res.nff ? (() => {
                const retest = res.nff.p_nff >= res.nff.threshold;
                return (
                  <div>
                    <Stamp tone={retest ? "violet" : "red"} rotate={-3}>{retest ? "RE-TEST BEFORE REMOVAL" : "REMOVE + REPLACE"}</Stamp>
                    <div className="mono text-[12px] mt-3">P(NFF) FOR {res.nff.lru}: <b>{fmtPct(res.nff.p_nff)}</b> · THRESHOLD {fmtPct(res.nff.threshold)}</div>
                    <div className="mt-1"><Meter value={res.nff.p_nff} color={retest ? "var(--s-depot)" : "var(--ink-3)"} /></div>
                    <div className="foot">{res.nff.recommendation}.</div>
                  </div>
                );
              })() : <div className="mono text-[12px] ink-3">SELECT THE SUSPECT LRU FOR A NO-FAULT-FOUND ESTIMATE.</div>}
            </Panel>
            <Panel title={`Fixed it before · ATA ${res.ata[0].ata}`} meta="REPEAT ≤30 D" pad={false}>
              {res.fix_effectiveness.length ? (
                <table className="ledger"><thead><tr><th>Action</th><th className="n">Cases</th><th className="n">Repeat</th></tr></thead>
                  <tbody>{res.fix_effectiveness.map((f: any) => <tr key={f.action_kind}><td>{f.action_kind}</td><td className="n">{f.cases}</td><td className="n">{fmtPct(f.repeat_rate)}</td></tr>)}</tbody></table>
              ) : <div className="pad mono text-[12px] ink-3">NO FLEET HISTORY FOR THIS CHAPTER.</div>}
            </Panel>
          </div>
          <div className="f700 min-w-0">
            <div className="fh"><h3>Similar past entries</h3><span>FLEET = THIS FLEET'S LOG (NOTIONAL) · MAINTNET = REAL GA LOGBOOKS</span></div>
            <div className="scroll-y max-h-[560px]">
              <table>
                <thead><tr><th style={{ width: 110 }}>Source</th><th>Defect</th><th>Rectification</th><th style={{ width: 64 }}>Match</th></tr></thead>
                <tbody>{res.similar.map((s: any) => (
                  <tr key={s.ref}>
                    <td>{s.source === "fleet" ? <Link to={`/aircraft/${s.tail}`}>{s.tail}</Link> : "MAINTNET"}<div className="text-[10.5px]" style={{ color: "var(--ink-3)" }}>{s.date ?? s.ref}</div>
                      {s.repeat_30d && <div className="redpen text-[10.5px] inline-block mt-1 whitespace-nowrap">REPEAT ≤30D</div>}</td>
                    <td>{s.problem}</td><td>{s.action}</td><td className="n">{fmtPct(s.similarity)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,400px)_minmax(0,1fr)] gap-4 mt-4">
        <Panel title="Snags by ATA" meta={<>2 YRS · <span style={{ color: "var(--s-depot)" }}>▮</span> NFF</>}>
          {stats.data ? by.map((r: any) => (
            <div key={r.ata} className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)_40px] items-center gap-2 py-[2px] mono text-[11px]">
              <span className="truncate">{r.ata} {r.system.toUpperCase()}</span>
              <span className="h-[8px] relative" style={{ background: "var(--rule-2)" }}>
                <span className="absolute left-0 top-0 bottom-0" style={{ width: `${(r.snags / maxBy) * 100}%`, background: "var(--ink-2)" }} />
                <span className="absolute left-0 top-0 bottom-0" style={{ width: `${(r.nff / maxBy) * 100}%`, background: "var(--s-depot)" }} />
              </span>
              <span className="text-right">{r.snags}</span>
            </div>
          )) : <Loading />}
        </Panel>
        <div className="f700 min-w-0">
          <div className="fh"><h3>Recent entries — all squadrons</h3><span>TO {today ? dataDtg(today) : ""}</span></div>
          <div className="scroll-y max-h-[470px]">
            <table>
              <thead><tr><th style={{ width: 92 }}>Date</th><th style={{ width: 70 }}>Tail</th><th style={{ width: 40 }}>ATA</th><th>Defect reported</th><th style={{ width: 120 }}>Finding</th></tr></thead>
              <tbody>{(recent.data || []).map((s) => (
                <tr key={s.snag_id}><td className="n">{s.date.slice(0, 10)}{s.filed_by && <div className="text-[10px]" style={{ color: "var(--blue-ink)" }}>{s.snag_id} · {s.filed_by}</div>}</td><td><Link to={`/aircraft/${s.tail}`}>{s.tail}</Link></td><td>{s.ata}</td><td>{s.text}</td>
                  <td><Stamp tone={s.finding === "NFF" ? "grey" : s.finding === "OPEN" ? "blue" : "red"} rotate={(s.snag_id.charCodeAt(s.snag_id.length - 1) % 5) - 2}>{s.finding}</Stamp></td></tr>))}</tbody>
            </table>
          </div>
        </div>
      </div>
    </Board>
  );
}
