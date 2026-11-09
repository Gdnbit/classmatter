import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { ArrowUp, Copy, Check, X } from "lucide-react"
import type { ChatCandidate } from "./workspace-chat"
import type { WorkspaceChatController } from "./useWorkspaceChat"
import { R1Dialog } from "./R1Dialog"
import type { Command, Session } from "./api"
import { ModelSwitcher } from "./ModelSwitcher"
import { userMessage } from "./user-facing"

const labels = { "class.create": "建立班级与学期", "class.update": "修改班级名称", "term.update": "更正学期信息", "student.create": "添加学生", "student.update_name": "更正学生姓名",
  "task.create": "建立任务", "task.update": "修改任务", "document.create": "创建工作文档", "document.revise": "修改工作文档" }
const states = { queued: "等待回复", running: "正在回复…", completed: "回复完成", failed: "回复失败，请稍后再试", cancelled: "已停止回复", unknown: "暂时无法确认回复结果" }
function AnswerActions({ text, duration }: { text: string; duration: number | null }) {
  const [copied, setCopied] = useState(false), [failed, setFailed] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setFailed(false); setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 2000)
    } catch { setCopied(false); setFailed(true) }
  }
  return <div className="r1-answer-actions">
    {duration !== null && <span>用时 {(duration / 1000).toFixed(1)} 秒</span>}
    <button type="button" aria-label="复制回答" onClick={() => void copy()}>{copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}{copied ? "已复制" : "复制回答"}</button>
    <span role="status">{failed ? "复制失败，请选择文字复制" : copied ? "已复制回答" : ""}</span>
  </div>
}
function CandidateContent({ value }: { value: ChatCandidate }) {
  return <>
    {"name" in value && <p>{"previous_name" in value && <>原名称：{value.previous_name} → </>}名称：{value.name}</p>}
    {"term_name" in value && <p>学期：{value.term_name} · {value.start_date} 至 {value.end_date}</p>}
    {"previous_start_date" in value && <p>起止：{value.previous_start_date} — {value.previous_end_date} → {value.start_date} — {value.end_date}</p>}
    {"title" in value && <p>标题：{value.title}</p>}
    {"status" in value && <p>状态：{value.status === "waiting" ? "等待别人" : value.status === "in-progress" ? "进行中" : "未开始"}</p>}
    {"body" in value && <details open><summary>核对文档正文（工作草稿，非正式事实）</summary><p className="r1-document-draft">{value.body}</p></details>}
  </>
}
export function WorkspaceChatHistory({ state: s }: { state: WorkspaceChatController }) {
  const [clear, setClear] = useState<{ thread: string; version: number } | null>(null)
  useLayoutEffect(() => { setClear(null) }, [s.history?.thread.thread_id, s.history?.thread.version])
  return <section aria-label="已保存的对话">
    <div className="r1-toolbar">
      <button disabled={s.working} onClick={s.refresh}>刷新对话</button>
      {s.history && <><button disabled={!s.fresh || s.working || s.lastActive || s.history.thread.status !== "active"} onClick={() => void s.control("archive")}>归档对话</button>
        <button disabled={!s.fresh || s.working || s.lastActive || s.history.thread.status === "cleared"} onClick={() => setClear({ thread: s.history!.thread.thread_id, version: s.history!.thread.version })}>清除聊天正文</button></>}
    </div>
    {s.history?.thread.status === "cleared" && <p>聊天正文已清除；原业务数据保持在各自页面中。</p>}
    {s.history?.next_before && <button disabled={s.working} onClick={() => void s.moreHistory()}>加载更早消息</button>}
    <div className="r1-messages">
      {s.pendingSend && !s.history?.turns.some(turn => turn.request_id === s.pendingSend?.request) && <article className="user" aria-label="你的消息"><p>{s.pendingSend.text}</p></article>}
      {s.history?.turns.map(turn => <div key={turn.turn_id}>
        {turn.user_text && <article className="user" aria-label="你的消息"><p>{turn.user_text}</p></article>}
        {turn.assistant_text && <article className="assistant" aria-label="助手回复"><p>{turn.assistant_text}</p><AnswerActions text={turn.assistant_text} duration={turn.duration_ms} /></article>}
        {turn.state !== "completed" && <p className="r1-muted">{states[turn.state]}</p>}
        {turn.state === "queued" && <button disabled={s.working || !s.fresh} onClick={() => void s.startQueued(turn)}>继续回复</button>}
        {turn.candidate && <section className="r1-card" aria-label="对话中的操作候选">
          <h2>{labels[turn.candidate.command]}</h2><CandidateContent value={turn.candidate} />
          {turn.action_receipt ? <p role="status">已保存</p>
            : <><p className="r1-muted">这项操作尚未保存。核对内容后预览，再确认执行。</p><button className="r1-primary" disabled={s.working || !s.fresh || s.history?.thread.status !== "active"} onClick={() => void s.preview(turn)}>预览这项操作</button></>}
        </section>}
      </div>)}
    </div>
    {s.status && <p role="status" className="r1-muted">{userMessage(s.status)}</p>}
    {s.pendingSend && <button disabled={s.working} onClick={() => void s.recoverSend()}>恢复消息</button>}
    {clear && clear.thread === s.history?.thread.thread_id && clear.version === s.history.thread.version && <R1Dialog titleId="workspace-chat-clear" onDismiss={() => setClear(null)}><h2 id="workspace-chat-clear">清除这段聊天正文？</h2>
      <p>仅清除这段本机聊天的消息和未提交候选；已保存的班级、学生、任务和文档不受影响。既有备份不会自动删除。</p>
      <button disabled={s.working || !s.fresh} onClick={() => { if (clear.thread !== s.history?.thread.thread_id || clear.version !== s.history.thread.version) return; setClear(null); void s.control("clear") }}>确认清除正文</button><button onClick={() => setClear(null)}>保留聊天</button></R1Dialog>}
  </section>
}
export function WorkspaceChatComposer({ state: s, session, modelRevision, onManageModels, onPreviewModel, onModelVerified, onError }: {
  state: WorkspaceChatController; session: Session; modelRevision: number;
  onManageModels: () => void; onPreviewModel: (command: Command) => Promise<void>;
  onModelVerified: (verified: boolean) => void; onError: (error: unknown) => void;
}) {
  return <form className="r1-composer" data-chat-fresh={s.fresh} data-chat-working={s.working} data-chat-pending={!!s.pendingSend} onSubmit={event => { event.preventDefault(); void s.send() }}>
    <textarea aria-label="输入消息" placeholder="随便聊聊，或告诉我你想创建、修改什么……" maxLength={2000} value={s.text}
      onChange={event => s.setText(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (s.canSend) void s.send() } }} />
    <div>
      <ModelSwitcher session={session} state={s.model} revision={modelRevision} disabled={s.anyWorking || s.lastActive || !!s.pendingSend}
        onManage={onManageModels} onPreview={onPreviewModel} onVerified={onModelVerified} onError={onError} />
      {s.lastActive ? <button type="button" aria-label="停止回复" onClick={() => void s.stop()}><X size={18} /></button>
        : <button aria-label="发送消息" disabled={!s.canSend || !s.text.trim()}><ArrowUp size={18} /></button>}
    </div>
  </form>
}
