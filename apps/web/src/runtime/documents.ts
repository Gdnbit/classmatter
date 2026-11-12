// Fixed document transport. No storage cache, retry, autosave or Agent dispatch.
import * as validators from "./document-validators.cjs"
import { ApiError, type Session, type Classroom, type CommandReceipt } from "./api"

type Scope = { document_id: string; class_id: string; term_id: string }
type Content = { title: string; body: string; format: "plain-text" | "markdown" }
export type DocumentCommand = Scope & (
  { command: "document.create" } & Content
  | { command: "document.revise"; expected_version: number } & Content
  | { command: "document.archive" | "document.restore"; expected_version: number }
)
export type DocumentMetadata = Scope & { title: string; format: Content["format"]; version: number;
  status: "draft" | "archived"; created_at: string; updated_at: string }
export type RevisionMetadata = { version: number; status: DocumentMetadata["status"]; title: string;
  format: Content["format"]; operation: DocumentCommand["command"]; created_by: string; created_at: string }
export type Revision = RevisionMetadata & { body: string }
export type DocumentView = Scope & Revision & { updated_at: string }
export type OfficeFormat = 'docx' | 'pptx'
const officeMedia = { docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }
export type DocumentPage<T> = { workspace_id: string; class_id: string; term_id: string;
  data: T[]; snapshot: string; next_offset: number | null }
export type DocumentPreview = { schema_version: "classmatter.document-preview.v1"; proposal_id: string;
  payload_hash: string; risk: "W2"; expires_at: string; payload: DocumentCommand }
type State = { schema_version: "class-os.command-status.v1"; status: "committed" | "not_committed" | "unavailable";
  proposal_id: string; payload_hash: string; receipt: CommandReceipt | null }
type Schema = Exclude<keyof typeof validators, "default">
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const hash = /^[a-f0-9]{64}$/
const mismatch = () => new Error("文档响应未通过范围、版本或契约核对；未确认保存，也未回退样例数据。")
function id(value: string) { if (typeof value !== "string" || !uuid.test(value)) throw mismatch(); return value }
function version(value: number) { if (!Number.isSafeInteger(value) || value < 1 || value > 2147483647) throw mismatch(); return value }
function calendar(value: unknown): void {
  if (!value || typeof value !== "object") return
  for (const [key, item] of Object.entries(value)) {
    if (["created_at", "updated_at", "expires_at"].includes(key) && typeof item === "string") {
      const time = new Date(item)
      if (!Number.isFinite(time.getTime()) || time.toISOString().slice(0, 19) !== item.slice(0, 19)) throw mismatch()
    } else if (item && typeof item === "object") calendar(item)
  }
}
function freeze<T>(value: T): T {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value) }
  return value
}
function decode<T>(schema: Schema, value: unknown): T {
  const validator = validators[schema], valid = validator(value); validator.errors = null
  if (!valid) throw mismatch()
  calendar(value)
  return freeze(value as T)
}
async function json<T>(schema: Schema, path: string, session: Session, body?: unknown, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted()
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin",
    cache: "no-store", redirect: "error", signal,
    headers: body === undefined ? {} : { "content-type": "application/json", "x-class-os-csrf": session.csrf_token },
    body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
  if (!response.headers.get("content-type")?.startsWith("application/json") || !response.body) throw mismatch()
  const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", { fatal: true })
  let text = "", bytes = 0
  try {
    while (true) {
      const item = await reader.read(); signal?.throwIfAborted()
      if (item.done) break
      bytes += item.value.byteLength
      if (bytes > 1024 * 1024) throw mismatch()
      text += decoder.decode(item.value, { stream: true })
    }
    text += decoder.decode()
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  signal?.throwIfAborted()
  return decode<T>(schema, JSON.parse(text))
}

export function documentClient(session: Session, classroom: Pick<Classroom, "class_id" | "term_id">) {
  const workspace = id(session.subject.workspace_id), owner = id(session.subject.owner_id)
  const classId = id(classroom.class_id), termId = id(classroom.term_id)
  const root = `/api/workspaces/${workspace}`, commands = `${root}/document-commands`
  const collection = `${root}/classes/${classId}/terms/${termId}/documents`
  function scoped(value: { class_id: string; term_id: string }) {
    if (value.class_id !== classId || value.term_id !== termId) throw mismatch()
  }
  function revision(value: RevisionMetadata) {
    if (value.created_by !== owner || (value.version === 1) !== (value.operation === "document.create")
      || (value.status === "archived") !== (value.operation === "document.archive")) throw mismatch()
  }
  function command(value: DocumentCommand) {
    const schema = value.command === "document.create" ? "create" : value.command === "document.revise" ? "revise" : "stateCommand"
    decode(schema, { ...value }); scoped(value)
  }
  function preview(value: DocumentPreview) { decode("preview", value); command(value.payload) }
  function receipt(value: CommandReceipt, proposal: DocumentPreview) {
    const payload = proposal.payload, wanted = payload.command === "document.create" ? 1 : payload.expected_version + 1
    if (value.resource_id !== payload.document_id || value.version !== wanted) throw mismatch()
    return value
  }
  function pagePath(path: string, page?: { offset: number; snapshot: string }) {
    if (!page) return path
    if (!Number.isSafeInteger(page.offset) || page.offset < 50 || page.offset >= 10000 || page.offset % 50
      || !hash.test(page.snapshot)) throw mismatch()
    return `${path}/pages/${page.snapshot}/${page.offset}`
  }
  function pageResult<T>(value: DocumentPage<T>, page?: { offset: number; snapshot: string }) {
    scoped(value)
    if (value.workspace_id !== workspace) throw mismatch()
    if ((page && value.snapshot !== page.snapshot) || (value.next_offset !== null
      && (value.data.length !== 50 || value.next_offset !== (page?.offset || 0) + 50))) throw mismatch()
    return value
  }
  return {
    async exportFile(documentId: string, number: number, format: OfficeFormat, signal?: AbortSignal) {
      signal?.throwIfAborted()
      if (!Object.prototype.hasOwnProperty.call(officeMedia, format)) throw mismatch()
      const path = `${collection}/${id(documentId)}/exports/${version(number)}/${format}`
      const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal })
      if (!response.ok) throw new ApiError(response.status, response.headers.get('x-request-id') || '')
      if (response.headers.get('content-type') !== officeMedia[format] || response.headers.get('x-classmatter-document-id') !== documentId
        || response.headers.get('x-classmatter-document-version') !== String(number) || !response.body) throw mismatch()
      const reader = response.body.getReader(), chunks: Uint8Array[] = []
      let count = 0
      try {
        while (true) {
          const item = await reader.read(); signal?.throwIfAborted()
          if (item.done) break
          count += item.value.byteLength
          if (count > 4 * 1024 * 1024) throw mismatch()
          chunks.push(item.value)
        }
      } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
      signal?.throwIfAborted()
      const bytes = new Uint8Array(count)
      let offset = 0
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
      if (bytes[0] !== 0x50 || bytes[1] !== 0x4b || count < 4) throw mismatch()
      return { blob: new Blob([bytes], { type: officeMedia[format] }), path }
    },
    async list(page?: { offset: number; snapshot: string }, signal?: AbortSignal) {
      const result = await json<DocumentPage<DocumentMetadata>>("listing", pagePath(collection, page), session, undefined, signal)
      const ids = new Set<string>()
      for (const item of result.data) { scoped(item); if (ids.has(item.document_id)) throw mismatch(); ids.add(item.document_id) }
      return pageResult(result, page)
    },
    async read(documentId: string, signal?: AbortSignal) {
      const result = await json<{ workspace_id: string; data: DocumentView }>("document", `${collection}/${id(documentId)}`, session, undefined, signal)
      scoped(result.data); revision(result.data)
      if (result.workspace_id !== workspace || result.data.document_id !== documentId) throw mismatch()
      return result.data
    },
    async history(documentId: string, page?: { offset: number; snapshot: string }, signal?: AbortSignal) {
      const result = await json<DocumentPage<RevisionMetadata> & { document_id: string }>("history",
        pagePath(`${collection}/${id(documentId)}/history`, page), session, undefined, signal)
      let previous = Infinity
      if (result.document_id !== documentId) throw mismatch()
      for (const item of result.data) { revision(item); if (item.version >= previous) throw mismatch(); previous = item.version }
      return pageResult(result, page)
    },
    async revision(documentId: string, number: number, signal?: AbortSignal) {
      const result = await json<{ document_id: string; workspace_id: string; class_id: string; term_id: string; data: Revision }>("revision",
        `${collection}/${id(documentId)}/revisions/${version(number)}`, session, undefined, signal)
      revision(result.data)
      scoped(result)
      if (result.workspace_id !== workspace || result.document_id !== documentId || result.data.version !== number) throw mismatch()
      return result.data
    },
    async preview(payload: DocumentCommand, signal?: AbortSignal) {
      command(payload)
      const result = await json<DocumentPreview>("preview", `${commands}/preview`, session, payload, signal)
      preview(result)
      const keys = Object.keys(payload) as (keyof DocumentCommand)[]
      if (keys.length !== Object.keys(result.payload).length || keys.some(key => payload[key] !== result.payload[key])) throw mismatch()
      return result
    },
    async approve(proposal: DocumentPreview, signal?: AbortSignal) {
      preview(proposal)
      const result = await json<{ approval: string }>("approval", `${commands}/approve`, session,
        { proposal_id: proposal.proposal_id, payload_hash: proposal.payload_hash }, signal)
      return result.approval
    },
    async reject(proposal: DocumentPreview, signal?: AbortSignal) {
      preview(proposal)
      await json("rejection", `${commands}/reject`, session, { proposal_id: proposal.proposal_id }, signal)
    },
    async commit(proposal: DocumentPreview, key: string, approval: string, signal?: AbortSignal) {
      preview(proposal); id(key)
      if (typeof approval !== "string" || approval.length < 32 || approval.length > 128) throw mismatch()
      return receipt(await json<CommandReceipt>("receipt", `${commands}/commit`, session,
        { proposal_id: proposal.proposal_id, idempotency_key: key, approval }, signal), proposal)
    },
    async status(proposal: DocumentPreview, key: string, signal?: AbortSignal) {
      preview(proposal)
      const result = await json<State>("state", `${commands}/${id(proposal.proposal_id)}/receipts/${id(key)}`, session, undefined, signal)
      if (result.proposal_id !== proposal.proposal_id || result.payload_hash !== proposal.payload_hash
        || (result.status === "committed") !== (result.receipt !== null)) throw mismatch()
      if (result.receipt) receipt(result.receipt, proposal)
      return result
    },
  }
}
