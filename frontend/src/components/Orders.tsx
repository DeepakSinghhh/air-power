import { useState } from "react";
import { postJSON, useApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Stamp } from "./glyphs";
import { Panel } from "./ui";

/** Orders issued by approved plans, with their owner and status — approval is the start of the loop, not the end. */
export function OrderTracker({ refreshKey = 0 }: { refreshKey?: number }) {
  const { user, can } = useAuth();
  const [tick, setTick] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const { data } = useApi<any>("/api/orders", [refreshKey, tick]);
  const orders: any[] = data?.orders ?? [];
  const update = async (id: string, status: string) => {
    setErr(null);
    try {
      await postJSON(`/api/orders/${id}`, { status });
      setTick((t) => t + 1);
    } catch (e) {
      setErr(String(e));
    }
  };
  const mayUpdate = (o: any) => can("order:update") && (user?.role === o.owner || user?.role === "STN CDR");
  return (
    <Panel title="Order tracker" meta={data ? `${data.outstanding} OUTSTANDING · ${data.actioned} ACTIONED` : "…"} pad={false}>
      {orders.length === 0 ? (
        <div className="pad mono text-[12px] ink-3">NO ORDERS YET. APPROVING AN OPERATION ORDER ISSUES ONE ORDER PER ACTION TO ITS OWNER.</div>
      ) : (
        <div className="scroll-y max-h-[380px]">
          <table className="ledger">
            <thead><tr><th>Order</th><th>Action</th><th>Owner</th><th>Status</th><th /></tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="m">{o.id}<div className="ink-3 text-[10.5px]">PLAN #{o.plan_seq}</div></td>
                  <td className="mono text-[11.5px]">{o.text}</td>
                  <td className="m">{o.owner}</td>
                  <td><Stamp tone={o.status === "ACTIONED" ? "green" : o.status === "CANCELLED" ? "grey" : "blue"} rotate={-2}>{o.status}</Stamp>
                    {o.history.length > 0 && <div className="mono text-[10px] ink-3 mt-1">BY {o.history[o.history.length - 1].by}</div>}</td>
                  <td className="whitespace-nowrap text-right">
                    {o.status === "ISSUED" && mayUpdate(o) && <>
                      <button className="tag" onClick={() => update(o.id, "ACTIONED")}>ACTIONED</button>{" "}
                      <button className="tag" onClick={() => update(o.id, "CANCELLED")}>CANCEL</button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {err && <div className="mono text-[11.5px] px-3 py-2" style={{ color: "var(--crit)" }}>✕ {err}</div>}
      <div className="foot px-3 pb-2">Each status change is written to the decision ledger (08 PROOF). Only the owner or STN CDR can update an order.</div>
    </Panel>
  );
}
