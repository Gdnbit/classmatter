import { useEffect, useRef, useState } from "react"
import { ArrowUp, X } from "lucide-react"
import type { ChatCandidate } from "./workspace-chat"
import type { WorkspaceChatController } from "./useWorkspaceChat"
import { R1Dialog } from "./R1Dialog"

const labels = { "class.create": "建立班级与学期", "class.update": "修改班级名称", "term.update": "更正学期信息", "student.create": "添加学生", "student.update_name": "更正学生姓名",
  "task.create": "建立任务", "task.update": "修改任务", "document.create": "创建工作文档", "document.revise": "修改工作文档" }
const states = { queued: "输入已保存，尚未启动", running: "运行中，尚无保存的回答", completed: "回答已保存", failed: "本轮失败，未自动重跑", cancelled: "本轮已取消", unknown: "本轮结果未知，未自动重跑" }
function CandidateContent({ value }: { value: ChatCandidate }) {
  return <>
    {"name" in value && <p>{"previous_name" in value && <>原名称：{value.previous_name} → </>}名称：{value.name}</p>}
    {"term_name" in value && <p>学期：{value.term_name} · {value.start_date} 至 {value.end_date}</p>}
    {"previous_start_date" in value && <p>起止：{value.previous_start_date} — {value.previous_end_date} → {value.start_date} — {value.end_date}</p>}
    {"title" in value && <p>标题：{value.title}</p>}
    {"status" in value && <p>状态：{value.status === "waiting" ? "等待别人" : value.status === "in-progress" ? "进行中" : "未开始"}</p>}
    {"body" in value && <details open><summary>核对文档正文（工作草稿，非正式事实）</summary><p className="r1-document-draft">{value.body}</p></details>}
    {"expected_version" in value && <small>基于版本 {value.expected_version}；保存时还会重新校验。</small>}
  </>
}
export function WorkspaceChatHistory({ state: s }: { state: WorkspaceChatController }) {
  const end = useRef<HTMLDivElement>(null), [clear, setClear] = useState(false)
  const latest = s.history?.turns.at(-1)
  useEffect(() => { if (latest) end.current?.scrollIntoView({ block: "nearest" }) }, [latest?.turn_id, latest?.state])
  return <section aria-label="已保存的对话">
    <div className="r1-toolbar"><span className="r1-muted">{s.fresh ? "聊天由本机数据库保存，普通聊天无需班级" : "正在核对聊天保存状态…"}</span>
      <button disabled={s.working} onClick={s.refresh}>重新读取对话</button>
      {s.history && <><button disabled={!s.fresh || s.working || s.lastActive || s.history.thread.status !== "active"} onClick={() => void s.control("archive")}>归档对话</button>
        <button disabled={!s.fresh || s.working || s.lastActive || s.history.thread.status === "cleared"} onClick={() => setClear(true)}>清除聊天正文</button></>}
    </div>
    {s.history?.thread.status === "cleared" && <p>聊天正文已清除；原业务数据保持在各自页面中。</p>}
    {s.history?.next_before && <button disabled={s.working} onClick={() => void s.moreHistory()}>加载更早消息</button>}
    <div className="r1-messages">
      {s.history?.turns.map(turn => <div key={turn.turn_id}>
        {turn.user_text && <article className="user"><small>你</small><p>{turn.user_text}</p></article>}
        {turn.assistant_text && <article className="assistant"><small>ClassMatter</small><p>{turn.assistant_text}</p></article>}
        {turn.state !== "completed" && <p className="r1-muted">{states[turn.state]}</p>}
        {turn.state === "queued" && <button disabled={s.working || !s.fresh} onClick={() => void s.startQueued(turn)}>继续已保存的本轮</button>}
        {turn.candidate && <section className="r1-card" aria-label="对话中的操作候选">
          <h2>{labels[turn.candidate.command]}</h2><CandidateContent value={turn.candidate} />
          {turn.action_receipt ? <p role="status">已保存 · 业务版本 {turn.action_receipt.version}</p>
            : <><p className="r1-muted">这项操作尚未保存。核对内容后预览，再确认执行。</p><button className="r1-primary" disabled={s.working || !s.fresh || s.history?.thread.status !== "active"} onClick={() => void s.preview(turn)}>预览这项操作</button></>}
        </section>}
        {turn.duration_ms !== null && <details className="r1-muted"><summary>本轮运行记录</summary><p>{states[turn.state]} · {turn.duration_ms} ms · 输入/输出Token：{turn.input_tokens ?? "未提供"} / {turn.output_tokens ?? "未提供"}。Token为供应商报告，不是计费确认。</p></details>}
      </div>)}
    </div>
    {s.status && <p role="status" className="r1-muted">{s.status}</p>}
    {s.pendingSend && <button disabled={s.working} onClick={() => void s.recoverSend()}>核对并恢复原输入（不重跑模型）</button>}
    <div ref={end} />
    {clear && <R1Dialog titleId="workspace-chat-clear" onDismiss={() => setClear(false)}><h2 id="workspace-chat-clear">清除这段聊天正文？</h2>
      <p>仅清除这段本机聊天的消息和未提交候选；已保存的班级、学生、任务和文档不受影响。既有备份不会自动删除。</p>
      <button disabled={s.working} onClick={() => { setClear(false); void s.control("clear") }}>确认清除正文</button><button onClick={() => setClear(false)}>保留聊天</button></R1Dialog>}
  </section>
}
export function WorkspaceChatComposer({ state: s }: { state: WorkspaceChatController }) {
  return <form className="r1-composer" onSubmit={event => { event.preventDefault(); void s.send() }}>
    <textarea aria-label="输入消息" placeholder="随便聊聊，或告诉我你想创建、修改什么……" maxLength={2000} value={s.text}
      onChange={event => s.setText(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (s.canSend) void s.send() } }} />
    <div><span className="r1-muted">聊天已接入数据库 · 涉及班级时才使用班级工具</span>
      <span className="r1-muted">{!s.model ? "正在核对模型…" : s.model.mode === "configured-api" ? `ClassMatter · ${s.model.configuration?.model}` : "未启用真实模型 · 当前为合成测试回答"}</span>
      {s.lastActive ? <button type="button" aria-label="停止 Agent" onClick={() => void s.stop()}><X size={18} /></button>
        : <button aria-label="发送消息" disabled={!s.canSend || !s.text.trim()}><ArrowUp size={18} /></button>}
    </div>
  </form>
}
