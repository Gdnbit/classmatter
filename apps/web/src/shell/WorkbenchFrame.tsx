import type { ReactNode } from "react"

// The frozen prototype layout. Data, navigation and command authority belong
// to its supplied controllers, never to this presentational frame.
export function WorkbenchFrame({ sidebar, header, inspector, mobileNav, children, workspaceClassName = "" }: {
  sidebar: ReactNode
  header: ReactNode
  inspector?: ReactNode
  mobileNav?: ReactNode
  children: ReactNode
  workspaceClassName?: string
}) {
  return <div className="app-shell">
    {sidebar}
    <div className="shell-main">
      {header}
      <div className="body-grid" data-inspector={!!inspector}>
        <main className={`workspace ${workspaceClassName}`.trim()}>{children}</main>
        {inspector}
      </div>
    </div>
    {mobileNav}
  </div>
}
