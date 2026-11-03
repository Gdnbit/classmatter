import { ChevronRight, ClipboardList } from "lucide-react"
import "./work-presentation.css"

export function WorkHeading({ title, description }: { title: string; description: string }) {
  return <div className="surface-title">
    <span className="surface-icon"><ClipboardList size={22} /></span>
    <div><p className="eyebrow">工作空间</p><h1>{title}</h1><p>{description}</p></div>
  </div>
}

export function WorkTabs({ items, current, onSelect }: {
  items: readonly { id: string; label: string; disabled?: boolean; explanation?: string }[]
  current: string; onSelect: (id: string) => void
}) {
  return <div className="tabbar" role="tablist" aria-label="工作分类">
    {items.map(item => <button key={item.id} disabled={item.disabled} title={item.explanation}
      role="tab" aria-selected={current === item.id} className={current === item.id ? "active" : ""}
      onClick={() => onSelect(item.id)}>{item.label}</button>)}
  </div>
}

export function WorkItemButton({ title, due, status, onSelect, className = "" }: {
  title: string; due: string; status: string; onSelect: () => void; className?: string
}) {
  return <button className={`work-item-button ${className}`.trim()} onClick={onSelect}>
    <strong>{title}</strong><span>{due}</span><em>{status}</em><ChevronRight size={16} />
  </button>
}
