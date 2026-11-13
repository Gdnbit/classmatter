import type { ReactNode } from "react"
import { ChevronLeft, Users } from "lucide-react"

// Original prototype presentation only. Callers supply authorized projections
// and actions; no fixtures, domain mutations or identity matching live here.
export function StudentPageTitle({ title, description }: { title: string; description: string }) {
  return <div className="surface-title">
    <span className="surface-icon"><Users size={22} /></span>
    <div><p className="eyebrow">班级学生</p><h1>{title}</h1>{description && <p>{description}</p>}</div>
  </div>
}

export function StudentViewSwitcher({ current, onSelect, connected = false, onOpenSeating }: {
  current: string; onSelect: (view: string) => void; connected?: boolean; onOpenSeating?: () => void
}) {
  const unavailable = (view: string) => connected && !["清单", "表格"].includes(view) && !(view === "座位" && onOpenSeating)
  return <div className="view-switcher" role="tablist" aria-label="学生视图切换">
    {["清单", "表格", "座位", "宿舍", "小队", "画布"].map(view => <button key={view}
      role="tab" aria-selected={current === view} className={current === view ? "active" : ""}
      disabled={unavailable(view)}
      title={unavailable(view) ? "暂不可用" : undefined}
      onClick={() => view === "座位" && onOpenSeating ? onOpenSeating() : onSelect(view)}>{view}</button>)}
  </div>
}

export type RosterRow = { id: string; name: string; cells: readonly [ReactNode, ReactNode, ReactNode] }
export function StudentRosterTable({ rows, columns, selectedId, onSelect, disabled = false }: {
  rows: readonly RosterRow[]; columns: readonly [string, string, string, string]
  selectedId?: string; onSelect: (id: string) => void; disabled?: boolean
}) {
  return <div className="data-table">
    <div className="table-head">{columns.map(column => <span key={column}>{column}</span>)}</div>
    {rows.map(row => <button key={row.id} data-student-id={row.id} disabled={disabled} aria-pressed={selectedId === row.id}
      className={`table-row${selectedId === row.id ? " selected" : ""}`} onClick={() => onSelect(row.id)}>
      <span><i className="avatar">{row.name[0]}</i>{row.name}</span>
      {row.cells.map((cell, index) => <span key={index}>{cell}</span>)}
    </button>)}
  </div>
}

export function StudentProfileHeader({ name, identity, description, onBack, actions }: {
  name: string; identity: string; description: string; onBack: () => void; actions: ReactNode
}) {
  return <>
    <button className="back-link" onClick={onBack}><ChevronLeft size={16} /> 返回学生列表</button>
    <header className="student-profile-head">
      <span className="profile-avatar">{name[0]}</span>
      <div><p className="eyebrow">学生详情</p><h1>{name}</h1><p>{identity}</p><p>{description}</p></div>
      {actions}
    </header>
  </>
}
