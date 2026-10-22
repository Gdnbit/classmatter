import { useEffect, useRef } from "react"
import { Archive, Bot, ClipboardList, Grid2X2, LayoutList, MoreHorizontal, Settings, Sparkles, Users, FolderOpen, Database, CalendarClock } from "lucide-react"
import type { Workspace } from "@/shell/types"

export default function MobileNav({ workspace, setWorkspace, moreOpen, setMoreOpen }: { workspace: Workspace; setWorkspace: (workspace: Workspace) => void; moreOpen: boolean; setMoreOpen: (open: boolean) => void }) {
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const primary = [["对话", "conversation", Sparkles], ["学生", "students", Users], ["视图", "views", LayoutList], ["工作", "work", ClipboardList]] as const
  const extra = [["总览", "dashboard", Grid2X2], ["数据与内容", "data", Database], ["AI 待处理", "inbox", Bot], ["自动化", "automation", CalendarClock], ["知识库", "knowledge", Archive], ["报告与导出", "reports", FolderOpen], ["设置", "settings", Settings]] as const
  useEffect(() => {
    if (!moreOpen) return
    menu.current?.querySelector<HTMLButtonElement>("button")?.focus()
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setMoreOpen(false)
    }
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMoreOpen(false); trigger.current?.focus() }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && menu.current?.contains(document.activeElement)) {
        event.preventDefault()
        const buttons = Array.from(menu.current.querySelectorAll("button"))
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement)
        const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length
        buttons[next]?.focus()
      }
    }
    const resize = () => { if (innerWidth > 767) setMoreOpen(false) }
    document.addEventListener("pointerdown", outside)
    document.addEventListener("keydown", keyboard)
    window.addEventListener("resize", resize)
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", keyboard); window.removeEventListener("resize", resize) }
  }, [moreOpen, setMoreOpen])
  return <>
    <nav className="mobile-nav" aria-label="移动端导航">
      {primary.map(([label, target, Icon]) => <button key={label} className={workspace === target ? "active" : ""} aria-current={workspace === target ? "page" : undefined} onClick={() => { setMoreOpen(false); setWorkspace(target) }}><Icon size={18} /><span>{label}</span></button>)}
      <button ref={trigger} className={moreOpen ? "active" : ""} aria-haspopup="menu" aria-expanded={moreOpen} aria-controls="mobile-more-menu" onClick={() => setMoreOpen(!moreOpen)}><MoreHorizontal size={19} /><span>更多</span></button>
    </nav>
    {moreOpen && <div ref={menu} id="mobile-more-menu" className="mobile-more" role="menu" aria-label="移动端更多功能">
      {extra.map(([label, target, Icon]) => <button role="menuitem" key={label} onClick={() => { setWorkspace(target); setMoreOpen(false) }}><Icon size={17} />{label}</button>)}
    </div>}
  </>
}
