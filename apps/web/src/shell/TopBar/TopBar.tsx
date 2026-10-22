import {
  ChevronRight,
  Clock3,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react"

import type { Workspace } from "@/shell/types"

import type { Phase } from "@/types/transaction"
import { useUiFeedback } from "@/store/UiFeedbackStore"
import { useDemoWork, attentionSummary } from "@/store/DemoWorkStore"
export default function TopBar({
  workspace,
  transaction,
  inspectorOpen,
  onInspector,
}: {
  workspace: Workspace
  transaction: Phase | null
  inspectorOpen: boolean
  onInspector: () => void
}) {
  const { notify, openDetail } = useUiFeedback()
  const { tasks } = useDemoWork()
  const workspaceLabels: Record<Workspace, string> = {
    conversation: "对话",
    dashboard: "总览",
    students: "学生",
    views: "视图",
    work: "工作",
    data: "数据与内容",
    roster: "名单事务",
    spreadsheet: "表格",
    document: "文档",
    seat: "座位",
    dorm: "宿舍",
    group: "分组",
    inbox: "AI 待处理",
    automation: "自动化",
    knowledge: "知识库",
    reports: "报告与导出",
    settings: "设置",
  }

  const pending =
    transaction && !["committed", "discarded"].includes(transaction)

  const controls = pending
    ? ["预览"]
    : workspace === "conversation"
      ? ["定时安排"]
      : workspace === "students" || workspace === "views"
        ? ["当前视图", "筛选"]
        : workspace === "seat"
          ? ["编辑布局", "约束"]
          : []

  return (
    <header className="topbar">
      <div className="crumb">
        <span>{pending ? "当前工作空间" : workspaceLabels[workspace]}</span>
        {pending && (
          <>
            <ChevronRight size={14} />
            <strong>{workspaceLabels[workspace]}</strong>
          </>
        )}
      </div>
      {workspace === "conversation" && (
        <button
          className="today attention-summary"
          onClick={() =>
            openDetail({
              eyebrow: "今日注意力摘要",
              title: `当前演示有 ${tasks.filter(t => t.state !== "done").length} 项需要留意`,
              description: "内容按责任状态聚合，不等同于全部班级数据。",
              sections: [
                { label: "需要我处理", value: `${tasks.filter(t => t.state === "mine").length} 项` },
                { label: "等待别人", value: `${tasks.filter(t => t.state === "waiting").length} 项` },
                { label: "可能遗漏", value: `${tasks.filter(t => t.state === "possible").length} 项` },
              ],
              actions: [{ label: "知道了", tone: "primary" }],
            })
          }
        >
          <Clock3 size={15} />
          {attentionSummary(tasks)}
        </button>
      )}
      <div className="bar-actions">
        {pending && <span className="draft-dot">编辑中 · 2 项未提交变更</span>}
        {controls.map((control) => (
          <button key={control} onClick={() => notify(`${control}仅为演示入口，未修改数据或建立真实定时任务`)}>
            {control}
          </button>
        ))}
        <button
          aria-label="更多操作"
          onClick={() =>
            openDetail({
              eyebrow: "页面操作",
              title: workspaceLabels[workspace],
              description: "可用操作会根据当前页面、选中对象和权限动态变化。",
              sections: [
                { label: "当前范围", value: "合成演示学校 · 合成演示班" },
                { label: "当前学期", value: "2026–2027学年上学期" },
              ],
              actions: [
                {
                  label: "复制页面链接",
                  tone: "primary",
                  onSelect: () => notify("页面链接已复制（演示）"),
                },
              ],
            })
          }
        >
          <MoreHorizontal size={18} />
          <span className="sr-only">更多</span>
        </button>
        <button
          className="icon-btn"
          onClick={onInspector}
          aria-label={inspectorOpen ? "收起检查器" : "打开检查器"}
        >
          {inspectorOpen ? (
            <PanelRightClose size={19} />
          ) : (
            <PanelRightOpen size={19} />
          )}
        </button>
      </div>
    </header>
  )
}
