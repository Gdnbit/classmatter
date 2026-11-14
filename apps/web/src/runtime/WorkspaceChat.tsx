import { useEffect, useRef, useState } from "react"
import { ArrowUp, Copy, Check, X, Plus, Image, FileText, Mic, Square, ShieldCheck, LoaderCircle } from "lucide-react"
import type { ChatCandidate, ChatTurn } from "./workspace-chat"
import type { WorkspaceChatController } from "./useWorkspaceChat"
import type { Command, Session } from "./api"
import { ModelSwitcher } from "./ModelSwitcher"
import { useComposerInput } from './useComposerInput'
import './composer.css'
import { SeatLayoutPreview } from './SeatLayoutPreview'
import { ChangeComparison } from './ChangeComparison'
import { DocumentExportActions } from './DocumentExportActions'
import { documentClient } from './documents'
import { DocumentBody } from './DocumentBody'

const labels: Record<string, string> = { "class.create": "建立班级与学期", "class.update": "修改班级名称", "term.update": "更正学期信息", "student.create": "添加学生", "student.update_name": "更正学生姓名",
  "record.create": "记录事实", "task.create": "建立任务", "task.update": "修改任务", "task.complete": "结束任务", "task.cancel": "取消任务", "document.create": "创建工作文档", "document.revise": "修改工作文档" }
const states = { queued: "等待回复", running: "正在回复…", completed: "回复完成", failed: "回复失败，请稍后再试", cancelled: "已停止回复", unknown: "暂时无法确认回复结果" }
Object.assign(labels, { 'exam.create': '建立考试', 'score.record': '记录成绩', 'seat.layout.create': '建立座位表', 'seat.assign': '安排座位', 'seat.swap': '交换座位' })
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
    {'subject' in value && <p>科目：{value.subject} · 满分：{value.maximum_score}</p>}
    {'score' in value && <p>成绩：{value.score ?? ({ absent: '缺考', exempt: '免考', 'not-recorded': '未录入', scored: '未录入' }[value.status])}</p>}
    {value.command === 'seat.layout.create' && <SeatLayoutPreview rows={value.rows} columns={value.columns} />}
    {'row' in value && <p>目标：{value.row} 排 {value.column} 座</p>}
    {'first_row' in value && <p>{value.first_row} 排 {value.first_column} 座 ↔ {value.second_row} 排 {value.second_column} 座</p>}
    {"status" in value && !('score' in value) && <p>状态：{({ waiting: '等待别人', 'in-progress': '进行中', 'not-started': '未开始', done: '已完成', cancelled: '已取消' } as Record<string, string>)[value.status]}</p>}
    {'fact_text' in value && <p>{value.fact_text}</p>}
    {"body" in value && <details open><summary>草稿正文</summary><p className="r1-document-draft">{value.body}</p></details>}
  </>
}
type DocumentExports = { session: Session; onError: (error: unknown) => void }
function SavedDocumentExports({ turn, context }: { turn: ChatTurn; context: DocumentExports }) {
  const candidate = turn.candidate, receipt = turn.action_receipt
  if (!candidate || (candidate.command !== 'document.create' && candidate.command !== 'document.revise')
    || !receipt || receipt.resource_id !== candidate.document_id
    || receipt.version !== (candidate.command === 'document.create' ? 1 : candidate.expected_version + 1)) return null
  // Export the approved version in this turn's scope, never the active class
  // or a newer document revision. QG rejects stale/archived versions on read.
  // History revalidation is not a scope change: only identity/thread/turn
  // unmount or version change cancels this independent read-only download.
  return <DocumentExportActions value={{ document_id: candidate.document_id, title: candidate.title, version: receipt.version }}
    api={documentClient(context.session, candidate)} enabled={true} unsaved={false} onError={context.onError} />
}
export function WorkspaceChatHistory({ state: s, documentExports }: { state: WorkspaceChatController; documentExports?: DocumentExports }) {
  return <section aria-label="已保存的对话">
    {s.history?.thread.status === "cleared" && <p>此对话已清空</p>}
    {s.history?.next_before && <button disabled={s.working} onClick={() => void s.moreHistory()}>加载更早消息</button>}
    <div className="r1-messages">
      {s.pendingSend && !s.history?.turns.some(turn => turn.request_id === s.pendingSend?.request) && <article className="user" aria-label="你的消息"><p>{s.pendingSend.text}</p></article>}
      {s.history?.turns.filter(turn => !(turn.origin === 'personal-agent' && turn.state === 'completed' && !turn.candidate && !turn.answer_required)).map(turn => <div key={turn.turn_id}>
        {turn.origin !== 'personal-agent' && turn.user_text && <article className="user" aria-label="你的消息"><p>{turn.user_text}</p></article>}
        {turn.assistant_text && <article className="assistant" aria-label="助手回复"><DocumentBody body={turn.assistant_text} format="markdown" /><AnswerActions text={turn.assistant_text} duration={turn.duration_ms} /></article>}
        {turn.state !== "completed" && <p className="r1-muted" role={turn.state === 'queued' || turn.state === 'running' ? 'status' : undefined}>{turn.state === 'queued' && s.working ? states.running : states[turn.state]}</p>}
        {turn.state === "queued" && !s.working && <button disabled={!s.canAct} onClick={() => void s.startQueued(turn)}>继续回复</button>}
        {turn.state === 'failed' && turn.request_id === s.history?.turns.at(-1)?.request_id && turn.user_text && !turn.candidate && !turn.action_receipt
          && <button aria-label="重试回复" disabled={!s.canSend} onClick={() => void s.retryFailed(turn)}>重试</button>}
        {turn.candidate && <section className="r1-card" aria-label="对话中的操作候选">
          <h2>{turn.candidate.command.startsWith('document.') && 'title' in turn.candidate && turn.candidate.title === '班级小结委托'
            ? turn.candidate.command === 'document.create' ? '持续整理班级小结' : '调整小结委托'
            : labels[turn.candidate.command]}</h2>
          {turn.change_preview ? <ChangeComparison preview={turn.change_preview} saved={!!turn.action_receipt} /> : <CandidateContent value={turn.candidate} />}
          {turn.action_receipt ? <><p role="status" className={turn.change_preview ? 'sr-only' : undefined}>已保存</p>
            {(turn.turn_id === s.history?.turns.at(-1)?.turn_id || documentExports && turn.candidate.command.startsWith('document.')) && <div className="r1-toolbar">
              {turn.turn_id === s.history?.turns.at(-1)?.turn_id && <button disabled={!s.canSend} onClick={() => void s.continueTask(turn)}>继续任务</button>}
              {documentExports && <SavedDocumentExports key={s.draftKey + '/' + turn.turn_id} turn={turn} context={documentExports} />}
            </div>}</>
            : <button className="r1-primary" disabled={!s.canAct} onClick={() => void s.preview(turn)}>预览这项操作</button>}
        </section>}
      </div>)}
    </div>
    {/* Normal progress belongs to the turn; only stale reads need a recovery action. */}
    {s.history && s.status && !s.fresh && !s.working && !s.pendingSend && <div role="status" className="r1-toolbar"><span>暂时无法更新对话</span><button onClick={s.refresh}>重试</button></div>}
    {s.pendingSend && <button disabled={s.working} onClick={() => void s.recoverSend()}>恢复消息</button>}
  </section>
}
export function WorkspaceChatComposer({ state: s, session, modelRevision, onManageModels, onPreviewModel, onModelVerified, onError }: {
  state: WorkspaceChatController; session: Session; modelRevision: number;
  onManageModels: () => void; onPreviewModel: (command: Command) => Promise<void>;
  onModelVerified: (verified: boolean) => void; onError: (error: unknown) => void;
}) {
  const capture = useComposerInput(s, session, onError)
  const [menu, setMenu] = useState<'files' | 'access' | null>(null), [dragging, setDragging] = useState(false)
  const tools = useRef<HTMLDivElement>(null), file = useRef<HTMLInputElement>(null), image = useRef<HTMLInputElement>(null)
  useEffect(() => { setMenu(null); setDragging(false) }, [s.draftKey])
  useEffect(() => {
    if (!menu) return
    const outside = (event: PointerEvent) => { if (!tools.current?.contains(event.target as Node)) setMenu(null) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); setMenu(null) } }
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [menu])
  const imports = (files: FileList | null) => { setMenu(null); if (files) void capture.files(Array.from(files)) }
  return <form className={`r1-composer composer-reference${dragging ? ' composer-dropping' : ''}`} data-chat-fresh={s.fresh} data-chat-refresh-revision={s.refreshRevision} data-chat-working={s.working} data-chat-pending={!!s.pendingSend}
    onDragOver={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); setDragging(true) } }}
    onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false) }}
    onDrop={event => { event.preventDefault(); setDragging(false); imports(event.dataTransfer.files) }}
    onSubmit={event => { event.preventDefault(); if (!capture.busy && !capture.recording) void s.send() }}>
    <textarea aria-label="输入消息" placeholder="发消息…" maxLength={2000} value={s.text}
      onChange={event => { capture.clearNotice(); s.setText(event.target.value) }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (s.canSend && !capture.busy && !capture.recording) void s.send() } }} />
    <div className="composer-toolbar">
      <div className="composer-tools" ref={tools}>
        <button type="button" className="composer-icon" aria-label="添加附件" title="添加附件" aria-expanded={menu === 'files'} disabled={capture.busy || capture.recording}
          onClick={() => setMenu(value => value === 'files' ? null : 'files')}><Plus size={21} /></button>
        <button type="button" className="composer-access" aria-label="操作权限" title="保存更改前需确认" aria-expanded={menu === 'access'} onClick={() => setMenu(value => value === 'access' ? null : 'access')}><ShieldCheck size={17} /></button>
        {menu === 'files' && <section className="composer-menu" aria-label="添加内容">
          <button type="button" onClick={() => { setMenu(null); image.current?.click() }}><Image size={17} />添加图片</button>
          <button type="button" onClick={() => { setMenu(null); file.current?.click() }}><FileText size={17} />导入文件文字</button>
        </section>}
        {menu === 'access' && <section className="composer-menu composer-access-menu" aria-label="当前操作范围"><strong>操作范围</strong><p>查看和整理已有信息</p><p>准备创建与修改</p><p>保存前由你核对确认</p></section>}
      </div>
      <span className="composer-spacer" />
      {s.lastActive && <LoaderCircle className="composer-spinner" size={16} aria-label="正在回复" />}
      <ModelSwitcher session={session} state={s.model} revision={modelRevision} disabled={s.anyWorking || s.lastActive || !!s.pendingSend || capture.busy || capture.recording}
        reasoning={s.reasoning} onReasoning={s.setReasoning}
        onManage={onManageModels} onPreview={onPreviewModel} onVerified={onModelVerified} onError={onError} />
      <button type="button" className={`composer-icon${capture.recording ? ' composer-recording' : ''}`} aria-label={capture.recording ? '完成录音并转文字' : '语音转文字'}
        title={capture.recording ? '完成录音并转文字' : '语音转文字'} disabled={capture.busy || !!s.recordingFile} onClick={() => void capture.microphone()}>{capture.recording ? <Square size={17} /> : <Mic size={19} />}</button>
      {s.lastActive ? <button type="button" className="composer-send" aria-label="停止回复" onClick={() => void s.stop()}><X size={18} /></button>
        : <button className="composer-send" aria-label="发送消息" disabled={!s.canSend || !s.text.trim() || capture.busy || capture.recording}><ArrowUp size={19} /></button>}
    </div>
    <input ref={image} type="file" accept=".png,.jpg,.jpeg,.webp" multiple hidden aria-label="选择图片文件" onChange={event => { imports(event.target.files); event.target.value = '' }} />
    <input ref={file} type="file" accept=".txt,.md,.csv,.tsv,.docx,.xlsx,.pptx,.pdf,.wav,.mp3,.webm" multiple hidden aria-label="选择内容文件" onChange={event => { imports(event.target.files); event.target.value = '' }} />
    {(capture.busy || capture.recording || capture.status) && <div className={capture.busy || capture.recording ? 'composer-feedback' : 'sr-only'} role="status">{capture.recording ? `正在录音 ${Math.floor(capture.seconds / 60)}:${String(capture.seconds % 60).padStart(2, '0')}` : capture.status}
      {(capture.busy || capture.recording) && <button type="button" onClick={capture.cancel} aria-label="取消识别">取消</button>}</div>}
    {capture.error && <p className="composer-error" role="alert">{capture.error}</p>}
    {s.recordingFile && !capture.busy && !capture.recording && <div className="composer-feedback" role="group" aria-label="待识别录音">
      <button type="button" onClick={capture.retryRecording}>识别录音</button>
      <button type="button" onClick={capture.discardRecording}>丢弃录音</button>
    </div>}
    {dragging && <p className="composer-drop-hint">松开以添加内容</p>}
  </form>
}
