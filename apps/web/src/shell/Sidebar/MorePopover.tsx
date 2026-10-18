import { createPortal } from "react-dom"

import { ClipboardList, FileText, Image, Paperclip, Plus } from "lucide-react"
import { useUiFeedback } from "@/store/UiFeedbackStore"
export default function MorePopover({
  trigger,
  pinned,
  onEnter,
  onLeave,
  onClose,
  onSelect,
  extras,
}: any) {
  const { notify } = useUiFeedback()
  if (!trigger) return null
  const rect = trigger.getBoundingClientRect()
  const quickTargets: Record<string, string> = {
    记录一件事: "conversation",
    新建任务: "work",
    上传文件: "data",
    批量识图: "inbox",
    "生成通知 / 材料": "reports",
  }
  return createPortal(
    <div
      className="more-overlay"
      style={{ top: rect.top - 6, left: rect.right + 8 }}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      tabIndex={-1}
    >
      <p>快捷操作</p>
      {[
        ["记录一件事", ClipboardList],
        ["新建任务", Plus],
        ["上传文件", Paperclip],
        ["批量识图", Image],
        ["生成通知 / 材料", FileText],
      ].map(([label, Icon]: any) => (
        <button
          key={label}
          onClick={() => {
            onSelect(quickTargets[label])
            onClose()
            notify(`${label}工作区已打开`)
          }}
        >
          <Icon size={16} />
          <span>{label}</span>
        </button>
      ))}
      <p>更多功能</p>
      {extras.map(([label, target, Icon, desc]: any) => (
        <button
          key={label}
          onClick={() => {
            onSelect(target)
            onClose()
          }}
        >
          <Icon size={16} />
          <span>
            {label}
            <small>{desc}</small>
          </span>
        </button>
      ))}
    </div>,
    document.body,
  )
}
