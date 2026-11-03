import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { FileText } from "lucide-react"
import { ApiError, type Classroom, type Session } from "./api"
import { documentClient, type DocumentCommand, type DocumentMetadata, type DocumentPage,
  type DocumentPreview, type DocumentView, type Revision, type RevisionMetadata } from "./documents"
import { R1Dialog } from "./R1Dialog"
import "./documents-workspace.css"

type Props = {
  session: Session; classroom: Classroom; documentId: string; canWrite: boolean; canEdit: boolean
  onSelect: (id: string) => void; onSaved: (id: string) => void
  onDirtyChange: (value: boolean) => void; onBusyChange: (value: boolean) => void
  onError: (error: unknown) => void; onReauthenticate: () => void
}
type Pending = { proposal: DocumentPreview; key: string; approval: string | null; unknown: boolean }
const time = (value: string) => new Date(value).toLocaleString("zh-CN", { hour12: false })
const operations = { "document.create": "新建", "document.revise": "修改", "document.archive": "归档", "document.restore": "恢复" }

// Same original document layout. Only the fixed client crosses QG/BCG; no
// Demo store, autosave, optimistic business mutation or renderer-side SQL.
export function DocumentsWorkspace(props: Props) {
  const { session, classroom, documentId, onDirtyChange, onBusyChange } = props
  const api = useMemo(() => documentClient(session, classroom),
    [session.csrf_token, session.subject.workspace_id, classroom.class_id, classroom.term_id])
  const [listing, setListing] = useState<DocumentPage<DocumentMetadata> | null>(null)
  const [current, setCurrent] = useState<DocumentView | null>(null)
  const [history, setHistory] = useState<DocumentPage<RevisionMetadata> | null>(null)
  const [historical, setHistorical] = useState<Revision | null>(null)
  const [tab, setTab] = useState("修改后")
  const [title, setTitle] = useState("")
  const [body, setBody] = useState("")
  const [format, setFormat] = useState<"plain-text" | "markdown">("plain-text")
  const [edited, setEdited] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [refresh, setRefresh] = useState(0)
  const lifetime = useRef(new AbortController())
  const working = useRef(false)
  const candidate = useRef(crypto.randomUUID())
  const textEditor = useRef<HTMLTextAreaElement>(null)
  const [anchor, setAnchor] = useState<{ title: string; offset: number; length: number } | null>(null)
  const outline = useMemo(() => format === "markdown"
    ? [...body.matchAll(/^#{1,6}[ \t]+([^\r\n]{1,80})$/gm)].slice(0, 100).map(match =>
      ({ title: match[1], offset: match.index, length: match[0].length })) : [], [body, format])
  const selection = useRef(documentId)
  selection.current = documentId
  const fresh = documentId === "new"
  const dirty = edited || pending !== null
  const writable = props.canEdit && !busy && !loading && !pending && (fresh || current?.status === "draft")

  useLayoutEffect(() => { onDirtyChange(dirty) }, [dirty, onDirtyChange])
  useLayoutEffect(() => { onBusyChange(busy) }, [busy, onBusyChange])
  useEffect(() => () => { onDirtyChange(false); onBusyChange(false) }, [onDirtyChange, onBusyChange])
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = "" } }
    window.addEventListener("beforeunload", guard)
    return () => window.removeEventListener("beforeunload", guard)
  }, [dirty])
  useLayoutEffect(() => {
    if (anchor && tab === "修改后" && textEditor.current) {
      textEditor.current.focus()
      textEditor.current.setSelectionRange(anchor.offset, anchor.offset + anchor.length)
    }
  }, [anchor, tab])
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller
    return () => controller.abort()
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setListing(null)
    api.list(undefined, controller.signal).then(value => {
      if (!controller.signal.aborted) setListing(value)
    }).catch(reason => {
      if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : "文档列表读取失败"); props.onError(reason) }
    })
    return () => controller.abort()
  }, [api, refresh])
  useEffect(() => {
    const controller = new AbortController()
    setCurrent(null); setHistory(null); setHistorical(null); setError(""); setEdited(false); setPending(null); setAnchor(null); setTab("修改后")
    setTitle(""); setBody(""); setFormat("plain-text")
    if (!documentId || fresh) { setLoading(false); candidate.current = crypto.randomUUID(); return () => controller.abort() }
    setLoading(true)
    Promise.all([api.read(documentId, controller.signal), api.history(documentId, undefined, controller.signal)])
      .then(([value, revisions]) => {
        if (controller.signal.aborted) return
        if (revisions.data[0]?.version !== value.version || revisions.data[0]?.status !== value.status
          || revisions.data[0]?.title !== value.title || revisions.data[0]?.format !== value.format)
          throw new Error("读取过程中版本发生变化，请重新读取文档；没有拼接不同版本。")
        setCurrent(value); setHistory(revisions); setTitle(value.title); setBody(value.body); setFormat(value.format)
      }).catch(reason => {
        if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : "文档读取失败"); props.onError(reason) }
      }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [api, documentId, refresh])

  async function run(action: () => Promise<void>) {
    if (working.current) return
    working.current = true; setBusy(true); setError("")
    try { await action() }
    catch (reason) {
      if (!lifetime.current.signal.aborted) {
        setError(reason instanceof ApiError && reason.status === 409
          ? "文档版本或列表已变化。草稿仍保留，请先复制需要的内容，再放弃本地编辑并重新读取；没有覆盖他人修改。"
          : reason instanceof Error ? reason.message : "操作失败，未确认保存")
        props.onError(reason)
      }
    } finally { working.current = false; if (!lifetime.current.signal.aborted) setBusy(false) }
  }
  async function preview(operation: DocumentCommand["command"]) {
    if (!props.canWrite || loading || pending) return
    setNotice("")
    const scope = { class_id: classroom.class_id, term_id: classroom.term_id,
      document_id: fresh ? candidate.current : documentId }
    const command: DocumentCommand = operation === "document.create" ? { ...scope, command: operation, title, body, format }
      : operation === "document.revise" ? { ...scope, command: operation, expected_version: current!.version, title, body, format }
      : { ...scope, command: operation, expected_version: current!.version }
    const proposal = await api.preview(command, lifetime.current.signal)
    if (!lifetime.current.signal.aborted && selection.current === documentId)
      setPending({ proposal, key: crypto.randomUUID(), approval: null, unknown: false })
  }
  function saved(id: string, receipt: string) {
    if (lifetime.current.signal.aborted || selection.current !== documentId) return
    setNotice(`已收到保存回执 ${receipt}，正在重新读取已保存内容。`)
    setPending(null); setEdited(false); setRefresh(value => value + 1); props.onSaved(id)
  }
  async function commit() {
    if (!pending || pending.unknown || !props.canWrite) return
    let approval = pending.approval
    if (!approval) approval = await api.approve(pending.proposal, lifetime.current.signal)
    const attempt = { ...pending, approval, unknown: true }
    setPending(attempt) // Lost response must never enable an automatic second write.
    const receipt = await api.commit(attempt.proposal, attempt.key, approval, lifetime.current.signal)
    saved(receipt.resource_id, receipt.receipt_id)
  }
  async function check() {
    if (!pending) return
    const state = await api.status(pending.proposal, pending.key, lifetime.current.signal)
    if (state.receipt) saved(state.receipt.resource_id, state.receipt.receipt_id)
    else if (state.status === "not_committed") {
      setPending({ ...pending, unknown: false }); setNotice("原请求尚未提交。可按原请求明确重试，或放弃预览；没有自动重放。")
    } else setNotice("原请求状态暂不可核对。请保留此页，稍后再次核对，不重复新建。")
  }
  async function reject() {
    if (!pending || pending.unknown) return
    await api.reject(pending.proposal, lifetime.current.signal)
    if (!lifetime.current.signal.aborted) setPending(null)
  }
  const present = fresh || current !== null
  return <div className="surface connected-documents">
    <div className="surface-title"><span className="surface-icon"><FileText size={22} /></span><div>
      <p className="eyebrow">工作空间</p><h1>文档</h1><p>同一班级与学期的工作草稿 · 保存前预览，保留版本。</p>
    </div></div>
    {error && <p role="alert" className="r1-error">{error}</p>}
    {notice && !pending && <p role="status" className="r1-muted">{notice}</p>}
    <div className="r1-toolbar">
      <button disabled={!props.canEdit || dirty || busy || loading} onClick={() => props.onSelect("new")}>新建文档</button>
      <button disabled={dirty || busy || loading} onClick={() => setRefresh(value => value + 1)}>重新读取文档</button>
      {edited && !pending && <button disabled={busy} onClick={() => { setEdited(false); setRefresh(value => value + 1) }}>放弃本地编辑并重新读取</button>}
    </div>
    <div className="document-layout">
      <aside aria-label="文档列表"><strong>班级文档</strong>
        {!listing && <p>{error ? "文档列表不可用，可重新读取。" : "正在读取文档列表…"}</p>}
        {listing?.data.length === 0 && <p>尚无已保存文档。</p>}
        {listing?.data.map(item => <button key={item.document_id} disabled={dirty || busy || loading}
          className={item.document_id === documentId ? "selected-outline" : ""} onClick={() => props.onSelect(item.document_id)}>
          {item.title}<small>版本 {item.version}{item.status === "archived" ? " · 已归档" : ""}</small>
        </button>)}
        {listing?.next_offset !== null && listing?.next_offset !== undefined && <button disabled={dirty || busy} onClick={() => void run(async () => {
          const next = await api.list({ offset: listing.next_offset!, snapshot: listing.snapshot }, lifetime.current.signal)
          if (new Set([...listing.data, ...next.data].map(item => item.document_id)).size !== listing.data.length + next.data.length)
            throw new Error("文档分页出现重复，未拼接结果，请重新读取。")
          if (!lifetime.current.signal.aborted) setListing({ ...next, data: [...listing.data, ...next.data] })
        })}>更多文档</button>}
        {present && <><strong>文档结构</strong><button disabled={busy} onClick={() => { setTab("修改后"); setAnchor({ title: "全文", offset: 0, length: 0 }) }}>全文</button>
          {outline.map(item => <button key={item.offset} disabled={busy} onClick={() => { setTab("修改后"); setAnchor(item) }}>{item.title}</button>)}
          <p>显示正文中前100个、80字以内的 Markdown 标题，不需要另行维护。</p></>}
      </aside>
      <article>
        {loading && <p role="status">正在读取已保存正文与版本…</p>}
        {!documentId && <p>从左侧选择文档，或新建工作草稿。</p>}
        {present && <>
          <div className="doc-tabs" aria-label="文档视图">{["原文", "修改后", "修订记录"].map(value => <button key={value}
            className={tab === value ? "active" : ""} onClick={() => setTab(value)}>{value}</button>)}</div>
          {anchor && <p className="document-anchor">当前章节：{anchor.title}</p>}
          {tab === "原文" && <><h2>{current?.title || "尚未保存"}</h2><pre className="document-text">{current ? current.body : "尚无已保存原文。"}</pre></>}
          {tab === "修改后" && <>
            <label>文档标题<input aria-label="文档标题" value={title} maxLength={80} readOnly={!writable}
              onChange={event => { setTitle(event.target.value); setEdited(true) }} /></label>
            <label>正文格式<select aria-label="正文格式" value={format} disabled={!writable} onChange={event => { setFormat(event.target.value as typeof format); setEdited(true) }}>
              <option value="plain-text">纯文本</option><option value="markdown">Markdown 文本</option></select></label>
            <label>文档正文<textarea ref={textEditor} aria-label="文档正文" value={body} maxLength={100000} readOnly={!writable}
              onChange={event => { setBody(event.target.value); setAnchor(null); setEdited(true) }} /></label>
            <p className="r1-muted">{body.length} / 100000 字符 · 未保存内容仅在当前页面；不会自动成为事实或对外发送。</p>
            <button className="document-save" disabled={!props.canWrite || !writable || !title.trim() || (!fresh && !edited)}
              onClick={() => void run(() => preview(fresh ? "document.create" : "document.revise"))}>保存草稿</button>
          </>}
          {tab === "修订记录" && <section aria-label="已保存文档版本">
            {!history && <p>尚无已保存版本。</p>}
            {history?.data.map(item => <button key={item.version} disabled={busy} onClick={() => void run(async () => {
              const value = await api.revision(documentId, item.version, lifetime.current.signal)
              if (!lifetime.current.signal.aborted && selection.current === documentId) setHistorical(value)
            })}>版本 {item.version} · {operations[item.operation]} · {time(item.created_at)}</button>)}
            {history?.next_offset !== null && history?.next_offset !== undefined && <button disabled={busy} onClick={() => void run(async () => {
              const next = await api.history(documentId, { offset: history.next_offset!, snapshot: history.snapshot }, lifetime.current.signal)
              if (next.data.length && next.data[0].version >= history.data[history.data.length - 1].version)
                throw new Error("版本分页出现重复或错序，未拼接结果，请重新读取。")
              if (!lifetime.current.signal.aborted && selection.current === documentId) setHistory({ ...next, data: [...history.data, ...next.data] })
            })}>更多版本</button>}
            {historical && <><h2>{historical.title} · 版本 {historical.version}</h2><pre className="document-text">{historical.body}</pre></>}
          </section>}
        </>}
      </article>
      <aside aria-label="文档版本与来源"><strong>版本与来源</strong><p>工作草稿，不是正式业务事实。</p>
        {current && <><p>版本 {current.version} · {current.status === "archived" ? "已归档，只读" : "可审阅草稿"}</p>
          <p>保存时间：{time(current.created_at)}</p><p>作者标识：{current.created_by}</p>
          <button disabled={busy || dirty || !props.canWrite} onClick={() => void run(() => preview(current.status === "archived" ? "document.restore" : "document.archive"))}>
            {current.status === "archived" ? "恢复文档" : "归档文档"}</button></>}
        <p>评论与材料引用尚未接入；此处不展示样例评论或伪造来源。</p>
        {error && <button disabled={busy || pending?.unknown} onClick={() => { setPending(null); props.onReauthenticate() }}>重新验证身份（预览失效）</button>}
      </aside>
    </div>
    {pending && <R1Dialog titleId="document-preview-title" busy={busy} onDismiss={pending.unknown ? undefined : () => void run(reject)}>
      <h2 id="document-preview-title">确认文档变更</h2>
      <p>{operations[pending.proposal.payload.command]} · 需要你明确批准后提交。正文仍是工作草稿。</p>
      {error && <p role="alert" className="r1-error">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {pending.unknown && <p role="status">提交结果尚未核对。请核对原请求，不要重复新建或关闭此页。</p>}
      <p>有效至 {time(pending.proposal.expires_at)}</p>
      <h3>已保存内容</h3><pre className="document-text">{current ? `${current.title}\n${current.body}` : "尚无已保存原文。"}</pre>
      <h3>拟保存内容</h3><pre className="document-text">{"body" in pending.proposal.payload
        ? `${pending.proposal.payload.title}\n${pending.proposal.payload.body}` : `${current?.title} · ${operations[pending.proposal.payload.command]}`}</pre>
      <details><summary>完整性摘要</summary>{pending.proposal.payload_hash}</details>
      <div className="r1-toolbar"><button disabled={busy || pending.unknown} onClick={() => void run(reject)}>放弃文档预览</button>
        <button disabled={busy} onClick={() => void run(check)}>核对原文档提交</button>
        <button disabled={busy || pending.unknown || !props.canWrite} onClick={() => void run(commit)}>明确批准并保存</button></div>
      {error && !pending.unknown && <><p>重新验证会使预览失效，请先复制需要保留的正文；不会自动重新提交。</p>
        <button disabled={busy} onClick={() => { setPending(null); props.onReauthenticate() }}>关闭预览并重新验证身份</button></>}
    </R1Dialog>}
  </div>
}
