import { useEffect, useRef } from "react"
import { ArrowUp, X } from "lucide-react"
import type { Student } from "./api"
import type { DurableController } from "./useDurableConversation"
import { AttributionLabel } from "./AttributionLabel"
import { R1Dialog } from "./R1Dialog"
import { userMessage } from "./user-facing"

export function DurableHistory({ state: s, canWrite, onDraft }: { state: DurableController; canWrite: boolean; onDraft: (title: string) => void }) {
  const end = useRef<HTMLDivElement>(null)
  const last = s.history?.history.messages.at(-1)?.message_id
  useEffect(() => { if (last) end.current?.scrollIntoView({ block: "nearest" }) }, [last])
  const current = s.history
  if (s.workspaceChat) return <section className="r1-messages" aria-label="普通聊天">
    {s.chatMessages.map((message, index) => <article key={index} className={message.role}><small>{message.role === "user" ? "你" : "ClassMatter"}</small><p>{message.text}</p></article>)}
    {s.status && <p role="status" className="r1-muted">{userMessage(s.status)}</p>}
  </section>
  return <section className="r1-durable" aria-label="已保存的对话" data-history-fresh={s.fresh}>
    <div className="r1-toolbar"><button disabled={s.blocked || s.needsClassroom} onClick={() => void s.refresh()}>重新读取对话</button>
      {!s.fresh && <span className="r1-muted">正在加载…</span>}</div>
    <details className="r1-card" open={!current}><summary>已保存的会话（{s.listing?.data.length || 0}）</summary>
      {s.text.trim() && <p className="r1-muted">{s.needsClassroom ? "首次建立班级时会保留当前草稿；刷新或关闭窗口不会保留。" : "切换班级、学期或会话前请先发送或清空未发送文字；不会把它带到另一范围。未发送文字不跨刷新保存。"}</p>}
      {s.listing?.data.map(item => <button key={item.thread_id} aria-current={current?.history.thread_id === item.thread_id ? "true" : undefined}
        disabled={s.blocked || !!s.text.trim()} onClick={() => s.select(item.thread_id)}>{item.title} · {item.status === "cleared" ? "已清除" : item.status === "archived" ? "已归档" : "有效"}</button>)}
      {!s.listing?.data.length && <p className="r1-muted">尚无已保存会话。发送第一条消息时会创建。</p>}
      {s.listing?.next_offset && <button disabled={s.blocked} onClick={() => void s.moreThreads()}>更多会话</button>}
    </details>
    {current && <>
      <div className="r1-toolbar"><input aria-label="会话名称" maxLength={80} value={s.title} disabled={s.blocked || !canWrite || current.history.status !== "active"} onChange={event => s.setTitle(event.target.value)} />
        <button disabled={s.blocked || !canWrite || !s.title.trim() || current.history.status !== "active"} onClick={() => void s.rename()}>保存名称</button>
        <button disabled={s.blocked || !canWrite || current.history.status !== "active" || s.active} onClick={() => void s.control("archive")}>归档对话</button>
        <button disabled={s.blocked || !canWrite || current.history.status === "cleared" || s.active} onClick={() => void s.control("clear")}>清除对话正文</button></div>
      <AttributionLabel value={current.thread_attribution} />
      <p className="r1-muted">固定范围：{current.student_id ? "学生个人跟进" : "全班"}。历史 AI 内容不是当前事实，引用只证明当时查询。</p>
      {current.next_before && <button disabled={s.blocked} onClick={() => void s.moreHistory()}>加载更早消息</button>}
      {current.history.status === "cleared" && <p role="status">正文已清除；事实与手工任务不受影响。</p>}
      <div className="r1-messages">{current.history.messages.map(message => {
        const result = current.results.find(item => item.message_id === message.message_id)
        const author = current.message_attributions.find(item => item.message_id === message.message_id)?.attribution
        return <article key={message.message_id} className={message.content.role}>
          <small>{message.content.role === "user" ? "你 · 已保存" : "ClassMatter · 已保存但未核验"}</small><p>{message.content.text}</p>
          <AttributionLabel value={author} />
          {result?.result.sources.map(source => <details className="r1-muted" key={source.source_id} data-source-id={source.source_id}><summary>当时的查询来源 · {new Date(source.as_of).toLocaleString("zh-CN")}</summary>
            <p>内容可能已更新，请查看最新记录。</p></details>)}
          {result?.result.draft && <section className="r1-card"><h3>未提交的任务草稿</h3><p>{result.result.draft.title}</p>
            <p className="r1-muted">草稿尚未保存为任务，请核对后提交。</p>
            <button disabled={s.blocked || !canWrite} onClick={() => onDraft(result.result.draft!.title)}>打开任务草稿并核对</button></section>}
        </article>
      })}<div ref={end} /></div>
      {s.active && <div className="r1-toolbar">
        {current.turns.at(-1)?.run.state === "queued" && <button disabled={s.blocked || !canWrite || !s.fresh} onClick={() => void s.startSaved(current.turns.at(-1)!)}>继续回复</button>}
        <button onClick={() => void s.stop()}>请求停止</button>
        <button disabled={s.blocked} onClick={() => void s.reconcile()}>刷新回复状态</button>
      </div>}
    </>}
    {s.status && <p role="status" className="r1-muted">{userMessage(s.status)}</p>}
    {s.pending && <R1Dialog titleId="d1-control-title" busy={s.working} onDismiss={s.dismissControl}>
      <h2 id="d1-control-title">{s.pending.preview.payload.command === "conversation.clear" ? "确认清除会话正文" : "确认归档会话"}</h2>
      <p>归档不是删除。清除会移除聊天正文/历史草稿，不删除已确认的学生事实或手工任务。清除需要最近 5 分钟内验证的身份；若过期，请先到设置重新验证。</p>
      <p>请确认是否继续。</p>
      <button disabled={s.working} onClick={() => void s.commitControl()}>{s.pending.attempted ? "重试保存" : "明确批准并提交"}</button>
      <button disabled={s.working} onClick={() => void s.checkControl()}>核对原提交结果</button>
      {!s.pending.attempted && <button disabled={s.working} onClick={s.dismissControl}>取消预览</button>}
      {s.status && <p role="status">{userMessage(s.status)}</p>}
    </R1Dialog>}
  </section>
}

export function DurableComposer({ state: s, students, canWrite }: { state: DurableController; students: Student[]; canWrite: boolean }) {
  const fixed = !!s.history
  const unavailableStudent = !fixed && !!s.student && !students.some(item => item.student_id === s.student && item.status === "active")
  const allowed = s.workspaceChat ? s.canChat && !s.blocked && navigator.onLine : canWrite && s.fresh && !s.blocked && !s.active && !unavailableStudent && (!fixed || s.history?.history.status === "active")
  return <form className="r1-composer" onSubmit={event => { event.preventDefault(); void s.send() }}>
    <textarea aria-label="输入消息" placeholder={s.workspaceChat ? "随便聊聊，或告诉我你想处理什么……" : "输入、查询或整理班级工作……"} maxLength={2000} value={s.text} disabled={s.blocked || !s.inputReady}
      onChange={event => s.setText(event.target.value)} onKeyDown={event => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (allowed) void s.send() }
      }} />
    <div>
      <label>助理<select aria-label="对话方式" value={s.mode === "chat" && !s.workspaceChat ? "class-chat" : s.mode} disabled={s.blocked} onChange={event => s.setMode(event.target.value as typeof s.mode | "class-chat")}>
        <option value="chat">聊天</option><option value="read">查询班级工作</option><option value="draft">准备班级任务草稿</option><option value="class-chat">关联班级讨论</option></select></label>
      {!fixed && s.mode === "read" && <label className="r1-agent-scope">查询范围<select aria-label="助理查询范围" value={s.student} disabled={s.blocked} onChange={event => s.setStudent(event.target.value)}>
        <option value="">全班当前工作</option>{unavailableStudent && <option value={s.student}>原学生已不可用，请重新选择</option>}{students.filter(item => item.status === "active").map(item => <option key={item.student_id} value={item.student_id}>{item.name} · 个人跟进</option>)}</select></label>}
      {s.working && s.isStreaming ? <button type="button" aria-label="停止回复" onClick={() => void s.stop()}><X size={18} /></button>
        : <button aria-label="发送消息" disabled={!allowed || !s.text.trim()}><ArrowUp size={18} /></button>}
    </div>
  </form>
}
