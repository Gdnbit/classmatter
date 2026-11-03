import type { ReactNode } from "react"

// Shared original sidebar presentation. Authority and data stay with callers.
export function SidebarFrame({ children, footer, overlay }: {
  children: ReactNode; footer: ReactNode; overlay?: ReactNode
}) {
  return <aside className="sidebar">
    <div className="sidebar-scroll">{children}</div>
    {footer}{overlay}
  </aside>
}
