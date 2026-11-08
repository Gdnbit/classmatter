import { createContext, useContext, useState, type ReactNode } from "react"
import { useUiFeedback } from "./UiFeedbackStore"

export type DemoTask = { id: string; title: string; state: "mine" | "waiting" | "possible" | "done"; due: string; source: string; workspaceId: string; studentId?: string }
const initial: DemoTask[] = [
  { id: "check", title: "合成清单信息最终核对", state: "mine", due: "明天 17:00", source: "合成通知样例", workspaceId: "midterm" },
  { id: "late", title: "合成学生01迟到后续", state: "mine", due: "今天 12:30", source: "合成课堂记录", workspaceId: "midterm", studentId: "99001" },
  { id: "follow", title: "合成返校跟进（未关联学生）", state: "mine", due: "已逾期", source: "合成待跟进示例", workspaceId: "parents" },
  { id: "notice", title: "合成通知频道 · 1 条通知尚未确认责任", state: "possible", due: "待判断", source: "合成通知样例", workspaceId: "parents" },
  { id: "reply", title: "合成学生05家长 · 等待补充信息", state: "waiting", due: "待回复", source: "合成沟通样例", workspaceId: "parents", studentId: "99005" },
  { id: "receipt", title: "家长会回执 · 等待班长收集", state: "waiting", due: "明天 16:00", source: "合成回执样例", workspaceId: "parents" },
]
type Value = { tasks: DemoTask[]; complete: (id: string) => void }
const Context = createContext<Value | null>(null)
export function DemoWorkStore({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState(initial)
  return <Context.Provider value={{ tasks, complete: id => setTasks(all => all.map(t => t.id === id ? { ...t, state: "done" } : t)) }}>{children}</Context.Provider>
}
export function useDemoWork() {
  const value = useContext(Context)
  if (!value) throw new Error("DemoWorkStore is required")
  return value
}
export function attentionSummary(tasks: DemoTask[]) {
  return `需要我处理 ${tasks.filter(t => t.state === "mine").length} 项 · 等待别人 ${tasks.filter(t => t.state === "waiting").length} 项 · 可能遗漏 ${tasks.filter(t => t.state === "possible").length} 项`
}

export function useDemoTaskDetails() {
  const { complete } = useDemoWork()
  const { openDetail, notify } = useUiFeedback()
  return (task: DemoTask) => openDetail({
    eyebrow: "演示事项 · 注意力状态",
    title: task.title,
    description: "当前事项详情",
    status: task.state === "done" ? "示例事项已完成" : "示例事项待处理",
    sections: [{ label: "时限 / 等待", value: task.due }, { label: "来源样例", value: task.source }, { label: "责任", value: "职责与分工待确认，不默认认定班主任最终负责" }],
    timeline: ["合成样例，未提供真实履职、审核或接手记录"],
    actions: task.state === "done" ? [{ label: "关闭", tone: "primary" }] : [
      { label: "稍后提醒", onSelect: () => notify("提醒暂不可用。") },
      { label: "标记完成", tone: "primary", onSelect: () => { complete(task.id); notify("已完成示例事项") } },
    ],
  })
}
