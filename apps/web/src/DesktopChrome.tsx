import { useEffect, useState } from "react"
import { ArrowLeft, ArrowRight, PanelLeft } from "lucide-react"
import "./desktop.css"

declare global {
  interface Window { classMatterDesktop?: { openMenu: (name: string) => void } }
}

export default function DesktopChrome() {
  const [collapsed, setCollapsed] = useState(false)
  useEffect(() => {
    document.documentElement.classList.add("desktop-host")
    return () => document.documentElement.classList.remove("desktop-host")
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle("desktop-sidebar-collapsed", collapsed)
    return () => document.documentElement.classList.remove("desktop-sidebar-collapsed")
  }, [collapsed])
  return (
    <header className="desktop-titlebar" aria-label="桌面窗口工具栏">
      <div className="desktop-navigation">
        <button aria-label="返回上一页" title="返回上一页" onClick={() => window.history.back()}><ArrowLeft size={16} /></button>
        <button aria-label="前进下一页" title="前进下一页" onClick={() => window.history.forward()}><ArrowRight size={16} /></button>
        <button aria-label="切换左侧栏" title="切换左侧栏" aria-pressed={collapsed} onClick={() => setCollapsed(!collapsed)}><PanelLeft size={16} /></button>
      </div>
      <nav className="desktop-menus" aria-label="桌面菜单">
        {[["application", "文件"], ["edit", "编辑"], ["view", "视图"], ["help", "帮助"]].map(([id, label]) => (
          <button key={id} aria-haspopup="menu" onClick={() => window.classMatterDesktop?.openMenu(id)}>{label}</button>
        ))}
      </nav>
      <span className="desktop-demo-badge">合成演示</span>
    </header>
  )
}
