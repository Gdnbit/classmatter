import { createPortal } from "react-dom"
import { useLayoutEffect, useRef, useState } from "react"

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
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 52, left: 8, maxHeight: "calc(100dvh - 68px)" })
  useLayoutEffect(() => {
    if (!trigger) return
    const update = () => {
      const rect = trigger.getBoundingClientRect()
      const inset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--desktop-bar-height")) || 0
      const maxHeight = Math.max(80, innerHeight - inset - 16)
      const height = Math.min(panelRef.current?.scrollHeight || maxHeight, maxHeight)
      setPosition({ top: Math.max(inset + 8, Math.min(rect.top - 6, innerHeight - height - 8)), left: Math.max(8, Math.min(rect.right + 8, innerWidth - 266)), maxHeight: `${maxHeight}px` })
    }
    const outside = (e: PointerEvent) => { if (!panelRef.current?.contains(e.target as Node) && !trigger.contains(e.target as Node)) onClose() }
    update()
    if (pinned) panelRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
    window.addEventListener("resize", update)
    window.addEventListener("scroll", update, true)
    document.addEventListener("pointerdown", outside)
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); document.removeEventListener("pointerdown", outside) }
  }, [trigger, pinned, onClose])
  if (!trigger) return null
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
      ref={panelRef}
      role="menu"
      aria-label="更多功能"
      style={position}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onKeyDown={e => {
        if (e.key === "Escape") { e.stopPropagation(); onClose(); trigger.focus() }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault()
          const items = Array.from(panelRef.current?.querySelectorAll<HTMLButtonElement>("button") || [])
          const index = items.indexOf(document.activeElement as HTMLButtonElement)
          const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (index + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length
          items[next]?.focus()
        }
      }}
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
