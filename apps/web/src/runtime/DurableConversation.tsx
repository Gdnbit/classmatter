import { useEffect, useRef } from "react"
import { ArrowUp, X } from "lucide-react"
import type { Student } from "./api"
import type { DurableController } from "./useDurableConversation"
import { AttributionLabel } from "./AttributionLabel"
import { R1Dialog } from "./R1Dialog"

export function DurableHistory({ state: s, canWrite, onDraft }: { state: DurableController; canWrite: boolean; onDraft: (title: string) => void }) {
  const end = useRef<HTMLDivElement>(null)
  const last = s.history?.history.messages.at(-1)?.message_id
  useEffect(() => { if (last) end.current?.scrollIntoView({ block: "nearest" }) }, [last])
  const current = s.history
  return <section className="r1-durable" aria-label="已保存的对话">
    <div className="r1-toolbar"><button disabled={s.blocked} onClick={() => void s.refresh()}>重新读取对话</button>
      <span className="r1-muted">{s.fresh ? "来自当前授权数据库" : "正在核对；上次快照不能用于提交"}</span></div>
    <details className="r1-card" open={!current}><summary>已保存的会话（{s.listing?.data.length || 0}）</summary>
      {s.text.trim() && <p className="r1-muted">切换班级、学期或会话前请先发送或清空未发送文字；不会把它带到另一范围。未发送文字不跨刷新保存。</p>}
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
          {result?.result.sources.map(source => <details className="r1-muted" key={source.source_id}><summary>当时的查询来源 · {new Date(source.as_of).toLocaleString("zh-CN")}</summary>
            <p>查询回执：{source.receipt_id}</p><p>来源工作区：{source.source_workspace_id} · 原拥有者：{source.source_owner_id}</p>
            <p>版本摘要：{source.projection_hash}</p><p>历史证明，不代表当前统计、正式事实或写入批准。</p></details>)}
          {result?.result.draft && <section className="r1-card"><h3>未提交的任务草稿</h3><p>{result.result.draft.title}</p>
            <p className="r1-muted">历史草稿尚未成为业务任务；采纳后仍需核对当前表单并预览、提交。</p>
            <button disabled={s.blocked || !canWrite} onClick={() => onDraft(result.result.draft!.title)}>打开任务草稿并核对</button></section>}
        </article>
      })}<div ref={end} /></div>
      {s.active && <div className="r1-toolbar">
        {current.turns.at(-1)?.run.state === "queued" && <button disabled={s.blocked || !canWrite || !s.fresh} onClick={() => void s.startSaved(current.turns.at(-1)!)}>明确启动已保存的本轮</button>}
        <button onClick={() => void s.stop()}>请求停止原运行</button>
        <button disabled={s.blocked} onClick={() => void s.reconcile()}>核对过期运行（不重跑）</button>
      </div>}
    </>}
    {s.status && <p role="status" className="r1-muted">{s.status}</p>}
    {s.pending && <R1Dialog titleId="d1-control-title" busy={s.working} onDismiss={s.dismissControl}>
      <h2 id="d1-control-title">{s.pending.preview.payload.command === "conversation.clear" ? "确认清除会话正文" : "确认归档会话"}</h2>
      <p>归档不是删除。清除会移除聊天正文/历史草稿，不删除已确认的学生事实或手工任务。清除需要最近 5 分钟内验证的身份；若过期，请先到设置重新验证。</p>
      <pre>{JSON.stringify(s.pending.preview.payload, null, 2)}</pre><p>风险 {s.pending.preview.risk} · 版本 {s.pending.preview.payload.expected_version}</p>
      <p className="r1-muted">摘要 {s.pending.preview.payload_hash}</p>
      <button disabled={s.working} onClick={() => void s.commitControl()}>{s.pending.attempted ? "使用原预览与同键重试提交" : "明确批准并提交"}</button>
      <button disabled={s.working} onClick={() => void s.checkControl()}>核对原提交结果</button>
      {!s.pending.attempted && <button disabled={s.working} onClick={s.dismissControl}>取消预览</button>}
      {s.status && <p role="status">{s.status}</p>}
    </R1Dialog>}
  </section>
}

export function DurableComposer({ state: s, students, canWrite }: { state: DurableController; students: Student[]; canWrite: boolean }) {
  const fixed = !!s.history
  const unavailableStudent = !fixed && !!s.student && !students.some(item => item.student_id === s.student && item.status === "active")
  const allowed = canWrite && s.fresh && !s.blocked && !s.active && !unavailableStudent && (!fixed || s.history?.history.status === "active")
  return <form className="r1-composer" onSubmit={event => { event.preventDefault(); void s.send() }}>
    <textarea aria-label="输入消息" placeholder="输入、查询或整理班级工作……" maxLength={2000} value={s.text} disabled={s.blocked || !s.inputReady}
      onChange={event => s.setText(event.target.value)} onKeyDown={event => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (allowed) void s.send() }
      }} />
    <div><span className="r1-muted">耐久会话 · 附件/语音仍未接入</span>
      <label>班级助理<select aria-label="Agent 交互模式" value={s.mode} disabled={s.blocked} onChange={event => s.setMode(event.target.value as typeof s.mode)}>
        <option value="read">查询当前工作</option><option value="draft">仅生成任务草稿</option><option value="chat">讨论，不调用工具</option></select></label>
      {!fixed && s.mode === "read" && <label className="r1-agent-scope">查询范围<select aria-label="助理查询范围" value={s.student} disabled={s.blocked} onChange={event => s.setStudent(event.target.value)}>
        <option value="">全班当前工作</option>{unavailableStudent && <option value={s.student}>原学生已不可用，请重新选择</option>}{students.filter(item => item.status === "active").map(item => <option key={item.student_id} value={item.student_id}>{item.name} · 个人跟进</option>)}</select></label>}
      {s.working && s.isStreaming ? <button type="button" aria-label="停止 Agent" onClick={() => void s.stop()}><X size={18} /></button>
        : <button aria-label="发送消息" disabled={!allowed || !s.text.trim()}><ArrowUp size={18} /></button>}
    </div>
  </form>
}
