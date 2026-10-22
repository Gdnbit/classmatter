import { useEffect, useRef, useState } from "react"

import {
  Archive,
  Bot,
  CalendarClock,
  ChevronRight,
  ClipboardList,
  Database,
  FolderOpen,
  Grid2X2,
  LayoutList,
  MoreHorizontal,
  Plus,
  Search,
  Settings,
  Users,
} from "lucide-react"

import { useConversationStore } from "@/store/ConversationStore"

import { useSessionStore } from "@/store/SessionStore"

import type { Workspace } from "@/shell/types"

import MorePopover from "./MorePopover"
import { useUiFeedback } from "@/store/UiFeedbackStore"
import { persistentWorkspaces } from "@/data/workspaces"
const navItems: { label: string; target: Workspace; icon: typeof Grid2X2 }[] = [
  { label: "总览", target: "dashboard", icon: Grid2X2 },
  { label: "学生", target: "students", icon: Users },
  { label: "视图", target: "views", icon: LayoutList },
  { label: "工作", target: "work", icon: ClipboardList },
  { label: "数据与内容", target: "data", icon: Database },
  { label: "自动化", target: "automation", icon: CalendarClock },
  { label: "设置", target: "settings", icon: Settings },
]

export default function Sidebar({
  workspace,
  setWorkspace,
}: {
  workspace: Workspace
  setWorkspace: (w: Workspace) => void
}) {
  const { activeConversationId, setConversation, navigate } = useSessionStore()
  const { createConversation, conversations, messagesByConversationId, renameConversation } = useConversationStore()
  const { openDetail } = useUiFeedback()
  const [moreOpen, setMoreOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [search, setSearch] = useState(false)
  const [query, setQuery] = useState("")
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeTimer = useRef<number | undefined>(undefined)
  const [renaming, setRenaming] = useState<string | null>(null)
  const filteredChats = conversations.filter(c => c.title.includes(query) || (messagesByConversationId[c.id] || []).some(m => m.text.includes(query)))
  const main = navItems.filter((x) =>
    ["总览", "学生", "工作"].includes(x.label),
  )
  const extras = [
    ["视图", "views", LayoutList, "切换班级数据投影"],
    ["数据与内容", "data", Database, "整理文件与候选内容"],
    ["AI 待处理", "inbox", Bot, "审核需要确认的候选"],
    ["自动化", "automation", CalendarClock, "查看计划与运行记录"],
    ["知识库", "knowledge", Archive, "引用规章与模板"],
    ["报告与导出", "reports", FolderOpen, "生成可审阅材料"],
    ["设置", "settings", Settings, "管理 ClassMatter 偏好"],
  ] as const
  const scheduleClose = () => {
    if (!pinned)
      closeTimer.current = window.setTimeout(() => setMoreOpen(false), 150)
  }
  const cancelClose = () => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current)
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMoreOpen(false)
        setSearch(false)
        setQuery("")
      }
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  }, [])
  return (
    <aside className="sidebar">
      <div className="sidebar-scroll">
        <button
          className="scope"
          onClick={() =>
            openDetail({
              eyebrow: "当前工作范围",
              title: "合成演示学校 · 合成演示班",
              description: "切换范围时，页面、对话和工具上下文会同步更新。",
              sections: [
                { label: "学期", value: "2026–2027学年上学期" },
                { label: "我的角色", value: "班主任" },
              ],
              actions: [{ label: "保持当前范围", tone: "primary" }],
            })
          }
        >
          <strong>合成演示学校</strong>
          <span>合成演示班 · 2026–2027学年上学期</span>
        </button>
        <button
          className="new-chat"
          onClick={() => {
            setWorkspace("conversation")
            setConversation(createConversation())
          }}
        >
          <Plus size={17} />
          新对话
        </button>
        <div className={`sidebar-search ${search ? "active" : ""}`}>
          <Search size={16} />
          {search ? (
            <input
              autoFocus
              aria-label="搜索当前演示对话"
              placeholder="搜索对话标题和消息"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          ) : (
            <button onClick={() => setSearch(true)}>搜索</button>
          )}
          {search && (
            <button
              className="search-close"
              onClick={() => {
                setSearch(false)
                setQuery("")
              }}
            >
              取消
            </button>
          )}
        </div>
        <nav className="workspace-nav" aria-label="主要工作组件">
          {main.map(({ label, target, icon: Icon }) => (
            <button
              key={label}
              onClick={() => setWorkspace(target)}
              className={workspace === target ? "nav-active" : ""}
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
          <button
            ref={triggerRef}
            onPointerEnter={() => {
              cancelClose()
              setMoreOpen(true)
            }}
          onPointerLeave={scheduleClose}
          onClick={() => {
            const next = !pinned
            setPinned(next)
            setMoreOpen(next)
          }}
            aria-expanded={moreOpen}
          >
            <MoreHorizontal size={17} />
            <span>更多</span>
            <ChevronRight size={14} />
          </button>
        </nav>
        {!query && (
          <section className="persistent-workspace">
            <p className="side-kicker">工作空间</p>
            {persistentWorkspaces.map(({name, id}) => (
              <button key={id} onClick={() => navigate({ domain: "work", rootSurfaceId: "WORKSPACE-OVERVIEW", modeSurfaceIds: [], params: { workspaceId: id } })}>
                <span className="status-ring" />
                {name}
              </button>
            ))}
          </section>
        )}
        <section className="chat-history">
          <p className="side-kicker">
            {query ? `搜索结果 · ${filteredChats.length}` : "聊天"}
          </p>
          {["本次演示会话"].map((group) => {
            const groupChats = filteredChats
            return groupChats.length ? (
              <div className="chat-group" key={group}>
                <small>{group}</small>
                {groupChats.map(({id, title}) => renaming === id ? (
                  <input key={id} aria-label="重命名对话" autoFocus defaultValue={title}
                    onBlur={e => { renameConversation(id, e.target.value); setRenaming(null) }}
                    onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { e.preventDefault(); setRenaming(null) } }} />
                ) : (
                  <button
                    key={id}
                    data-conversation-id={id}
                    aria-current={activeConversationId === id ? "page" : undefined}
                    className={
                      activeConversationId === id &&
                      workspace === "conversation"
                        ? "conversation-item active"
                        : "conversation-item"
                    }
                    onClick={() => {
                      setConversation(id)
                      setWorkspace("conversation")
                      setSearch(false)
                      setQuery("")
                    }}
                    onDoubleClick={() => setRenaming(id)}
                    title="双击重命名对话"
                  >
                    <span>{title}</span>
                    <MoreHorizontal className="chat-more" size={15} />
                  </button>
                ))}
              </div>
            ) : null
          })}
          {query && filteredChats.length === 0 && (
            <p className="sidebar-empty">没有找到相关对话</p>
          )}
        </section>
      </div>
      <button className="user-area" onClick={() => setWorkspace("settings")}>
        <span className="avatar">班</span>
        <span>
          班主任<small>合成演示学校</small>
        </span>
        <MoreHorizontal size={17} />
      </button>
      {moreOpen && (
        <MorePopover
          trigger={triggerRef.current}
          pinned={pinned}
          onEnter={cancelClose}
          onLeave={scheduleClose}
          onClose={() => {
            setPinned(false)
            setMoreOpen(false)
          }}
          onSelect={setWorkspace}
          extras={extras}
        />
      )}
    </aside>
  )
}
