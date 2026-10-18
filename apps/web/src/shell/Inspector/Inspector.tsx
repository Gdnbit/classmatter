import { MoreHorizontal } from "lucide-react"

import StudentPanel from "./StudentPanel"
import ScopePanel from "./ScopePanel"
import TransactionPanel from "./TransactionPanel"
import { useUiFeedback } from "@/store/UiFeedbackStore"
export default function Inspector(props: any) {
  const { openDetail } = useUiFeedback()
  return (
    <aside className="inspector">
      <div className="inspector-top">
        <p>上下文检查器</p>
        <button
          aria-label="检查器选项"
          onClick={() =>
            openDetail({
              eyebrow: "上下文检查器",
              title: "显示内容",
              description:
                "检查器只展示当前页面和当前选中对象的上下文，不会扩大数据访问范围。",
              sections: [
                { label: "当前范围", value: "合成演示班" },
                {
                  label: "选中对象",
                  value: props.activeStudent?.name || "当前班级",
                },
              ],
              actions: [{ label: "关闭", tone: "primary" }],
            })
          }
        >
          <MoreHorizontal size={18} />
        </button>
      </div>
      {props.activeStudent ? (
        <StudentPanel
          activeStudent={props.activeStudent}
          onSelect={props.onSelect}
        />
      ) : (
        <ScopePanel />
      )}
      {props.transaction && <TransactionPanel {...props} />}
    </aside>
  )
}
