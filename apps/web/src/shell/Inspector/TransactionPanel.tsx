import { AlertTriangle, Check, ChevronRight } from "lucide-react";
import { useTransactionSession } from "@/state/TransactionSessionProvider";
import { useMockDomainStore } from "@/store/MockDomainStore";
import { projectSeatPlan } from "@/demo/seat-plan";
export default function TransactionPanel({transaction,onDiscard,onCommit,onConfirmCommit,onCancelConfirm,onUnknown,onCheck}:any) {
  const { plan, error } = useTransactionSession();
  const { students } = useMockDomainStore();
  if (!plan || transaction === "discarded") return null;
  let issue = error;
  if (transaction !== "committed") { try { projectSeatPlan(students, plan); } catch (e) { issue = (e as Error).message; } }
  return <>
    <section><p className="inspect-label">座位调整 · 仅本次演示</p><div className="diff">
      {plan.changes.map(c => <div key={c.studentId}><strong>{c.name} <small>{c.studentId}</small></strong><span>{c.before}<ChevronRight size={12}/>{c.after}</span></div>)}
    </div></section>
    <section><p className="inspect-label">验证</p><p className={issue ? "warning" : "valid"}>{issue ? <AlertTriangle size={16}/> : <Check size={16}/>}{issue || "已校验：身份、快照、一人一座与一座一人"}</p>
      {transaction === "committed" && <p className="valid">已应用到当前演示内存；未写入业务数据库</p>}
      {transaction === "outcome-unknown" && <p className="warning">模拟状态待确认；没有提交到服务器</p>}
    </section>
    {transaction === "confirming" ? <div className="confirm-action"><strong>确认应用这两项演示变更？</strong><p>{plan.changes.map(c => c.name).join("与")}；仅更新当前演示内存。</p><div><button onClick={onCancelConfirm}>返回预览</button><button disabled={!!issue} className="primary" onClick={onConfirmCommit}>确认应用</button></div></div>
      : transaction !== "committed" && <div className="inspector-actions"><button onClick={onDiscard}>放弃修改</button><button disabled={!!issue || transaction === "outcome-unknown"} className="primary" onClick={onCommit}>应用变更</button></div>}
    {transaction === "preview-ready" && <button className="demo-unknown" onClick={onUnknown}>演示：提交状态待确认</button>}
    {transaction === "outcome-unknown" && <button className="primary wide" onClick={onCheck}>检查状态</button>}
  </>
}
