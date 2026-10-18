import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react"
import { localDateTimeToUtc } from "./local-time"
import {
  ArrowUp,
  ClipboardList,
  MessageSquare,
  Plus,
  Settings,
  Users,
  LayoutDashboard,
  X,
  LogOut,
  RefreshCw,
} from "lucide-react"
import {
  ApiError,
  request,
  scope,
  workspace,
  type Session,
  type Classroom,
  type TermMetadata,
  type Student,
  type Activity,
  type Command,
  type Proposal,
  type RecordItem,
  type TaskItem,
  type Identifier,
  type Duplicate,
  type QuerySource,
  type AuditPage,
  type CommandReceipt,
} from "./api"
import "./runtime.css"
import { consumeEvents } from "./events"
import { identityRequest, IdentityOutcomeUnknown, logoutIdentity } from "./identity"
import { R1Dialog } from "./R1Dialog"
import { ModelConfigurationForm } from "./ModelConfiguration"
import { createScopedConversation, parseRecordNoteCandidate, type RecordNoteCandidate } from "./agent-conversation"
import { decodeApproval, decodeCommandReceipt, decodeCommandState } from "./command-receipts"
import { decodeTermMetadata } from "./term-metadata"

const kinds: Record<string, string> = {
  ordinary_fact: "普通事实",
  teacher_observation: "教师观察",
  attendance_late_fact: "迟到事实",
  attendance_absent_fact: "缺勤事实",
  leave_requested_fact: "请假申请事实",
  leave_approved_fact: "请假批准事实",
  leave_returned_fact: "销假事实",
  homework_missing_fact: "作业未交事实",
  homework_submitted_fact: "作业补交事实",
  discipline_fact: "纪律事实（需批准）",
  conversation_fact: "谈话事实（需批准）",
}
const states: Record<TaskItem["status"], string> = {
  "not-started": "未开始",
  "in-progress": "进行中",
  waiting: "等待别人",
  done: "已完成",
  cancelled: "已取消",
}
const localNow = () => {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}
const displayTime = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "未设时间"
const localPreciseNow = () => {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 23)
}
const localDateValue = (value: string | null) => {
  if (!value) return ""
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 23)
}
type Page = "conversation" | "dashboard" | "students" | "work" | "settings"
type AgentInteraction = "read" | "draft" | "record-note" | "chat"
type Form = "class" | "class-edit" | "term-edit" | "student" | "student-name" | "record" | "task" | "task-edit" | "identifier" | "identifier-edit" | "revise" | "complete" | "cancel" | "reauth" | "reissue" | "logout-all" | null
type Pending = {
  proposal: Proposal
  key: string
  approval?: string
}

export default function R1App() {
  const [modelRevision, setModelRevision] = useState(0)
  const [modelUncertain, setModelUncertain] = useState(false)
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState("")
  const [page, setPage] = useState<Page>("conversation")
  const [classes, setClasses] = useState<Classroom[]>([])
  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [students, setStudents] = useState<Student[]>([])
  const [activity, setActivity] = useState<Activity | null>(null)
  const [identifiers, setIdentifiers] = useState<Identifier[]>([])
  const [replacingIdentifier, setReplacingIdentifier] = useState<Identifier | null>(null)
  const [duplicates, setDuplicates] = useState<Duplicate[]>([])
  const [selectedStudent, setSelectedStudent] = useState("")
  const [search, setSearch] = useState("")
  const [form, setForm] = useState<Form>(null)
  const [termMetadata, setTermMetadata] = useState<Readonly<TermMetadata> | null>(null)
  const [record, setRecord] = useState<RecordItem | null>(null)
  const [task, setTask] = useState<TaskItem | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(true)
  const [notice, setNotice] = useState("")
  const [exportId, setExportId] = useState("")
  const [issuedCodes, setIssuedCodes] = useState<string[] | null>(null)
  const [auditPage, setAuditPage] = useState<AuditPage | null>(null)
  const auditOpener = useRef<HTMLElement | null>(null)
  const [message, setMessage] = useState("")
  const [agentMode, setAgentMode] = useState<AgentInteraction>("read")
  const [agentStudent, setAgentStudent] = useState("")
  const [conversationId, setConversationId] = useState("")
  const [agentStatus, setAgentStatus] = useState("")
  const [draftTitle, setDraftTitle] = useState("")
  const [agentDraft, setAgentDraft] = useState<string | null>(null)
  const [agentRecordNote, setAgentRecordNote] = useState<RecordNoteCandidate | null>(null)
  const [recordNoteQuote, setRecordNoteQuote] = useState("")
  const runningAgent = useRef<AbortController | null>(null)
  const [messages, setMessages] = useState<{
    role: string
    text: string
    sources?: QuerySource[]
  }[]>([])
  const alive = useRef(true)
  const termLoad = useRef(0)
  const loading = useRef(0)
  const conversationViewport = useRef<HTMLDivElement>(null)
  const conversationContent = useRef<HTMLDivElement>(null)
  const messageInput = useRef<HTMLTextAreaElement>(null)
  const followingConversation = useRef(true)
  const observedMessages = useRef(0)
  const [newReply, setNewReply] = useState(false)
  const scrollToLatest = useCallback(() => {
    const viewport = conversationViewport.current
    if (viewport) viewport.scrollTop = viewport.scrollHeight
    setNewReply(false)
  }, [])
  useLayoutEffect(() => {
    if (page !== "conversation" || checking || !session) return
    const appended = messages.length > observedMessages.current
    observedMessages.current = messages.length
    if (!messages.length) {
      followingConversation.current = true
      setNewReply(false)
      if (conversationViewport.current) conversationViewport.current.scrollTop = 0
    } else if (followingConversation.current) scrollToLatest()
    else if (appended && messages[messages.length - 1].role === "assistant") setNewReply(true)
  }, [messages, page, checking, session?.csrf_token, scrollToLatest])
  useEffect(() => {
    const viewport = conversationViewport.current, content = conversationContent.current
    if (page !== "conversation" || checking || !session || !viewport || !content) return
    let observing = true
    const observer = new ResizeObserver(() => {
      if (observing && followingConversation.current && content.querySelector("article")) scrollToLatest()
    })
    observer.observe(viewport); observer.observe(content)
    return () => { observing = false; observer.disconnect() }
  }, [page, checking, session?.csrf_token, session?.subject.workspace_id, scrollToLatest])
  useEffect(() => {
    runningAgent.current?.abort()
    setConversationId(""); setMessages([]); setAgentDraft(null); setAgentRecordNote(null); setRecordNoteQuote(""); setAgentStatus("")
    setAgentStudent("")
  }, [session?.csrf_token, session?.subject.workspace_id, classroom?.class_id, classroom?.term_id])
  useEffect(() => () => { runningAgent.current?.abort() }, [])
  useEffect(() => { setAuditPage(null) }, [session?.csrf_token, classroom?.class_id, classroom?.term_id])
  useEffect(() => { termLoad.current++; setTermMetadata(null) }, [session?.csrf_token, classroom?.class_id, classroom?.term_id])
  const fail = useCallback((reason: unknown) => {
    setError(reason instanceof Error ? reason.message : "操作失败")
    if ((reason instanceof ApiError && reason.status === 401) || reason instanceof IdentityOutcomeUnknown) {
      loading.current++
      runningAgent.current?.abort()
      setSession(null)
      setPage("conversation")
      setSelectedStudent("")
      setRecord(null)
      setTask(null)
      setClassroom(null)
      setClasses([])
      setStudents([])
      setActivity(null)
      setIdentifiers([])
      setReplacingIdentifier(null)
      setDuplicates([])
      setPending(null)
      setForm(null)
      setIssuedCodes(null)
      setExportId("")
      setMessages([])
      setMessage("")
      setConversationId(""); setAgentDraft(null); setAgentRecordNote(null); setRecordNoteQuote(""); setAgentStatus(""); setDraftTitle("")
      setAuditPage(null)
    }
  }, [])

  useEffect(() => {
    alive.current = true
    identityRequest("session", "/api/identity/session")
      .then((value) => {
        if (alive.current) setSession(value)
      })
      .catch((reason) => {
        if (
          alive.current &&
          !(reason instanceof ApiError && reason.status === 401)
        )
          fail(reason)
      })
      .finally(() => {
        if (alive.current) setChecking(false)
      })
    return () => {
      alive.current = false
    }
  }, [fail])

  const reload = useCallback(
    async (chosen?: Classroom | null) => {
      if (!session) return
      const generation = ++loading.current
      setRefreshing(true)
      try {
      const history = await request<{ data: Classroom[] }>(
        `${workspace(session)}/classes`,
      )
      const target =
        chosen === undefined
          ? history.data.find(
              (item) => item.class_id === classroom?.class_id,
            ) ||
            history.data.find((item) => item.status === "active") ||
            history.data[0] ||
            null
          : chosen ? history.data.find(item => item.class_id === chosen.class_id) || null : null
      let data: {
        roster: Student[]
        activity: Activity
        identifiers: Identifier[]
        duplicates: Duplicate[]
      } | null = null
      if (target) {
        const base = scope(session, target)
        const [roster, events, ids, dupes] = await Promise.all([
          request<{ data: Student[] }>(`${base}/students`),
          request<{ data: Activity }>(`${base}/activity`),
          request<{ data: Identifier[] }>(`${base}/identifiers`),
          request<{ data: Duplicate[] }>(`${base}/duplicates`),
        ])
        data = {
          roster: roster.data,
          activity: events.data,
          identifiers: ids.data,
          duplicates: dupes.data,
        }
      }
      if (generation !== loading.current || !alive.current) return
      setClasses(history.data)
      setClassroom(target)
      setStudents(data?.roster || [])
      setActivity(data?.activity || null)
      setIdentifiers(data?.identifiers || [])
      setDuplicates(data?.duplicates || [])
      setError("")
      } catch (reason) {
        // A revoked old-session query cannot clear the new authenticated
        // session or its one-time kit after identity rotation.
        if (generation === loading.current && alive.current) throw reason
      } finally {
        if (generation === loading.current && alive.current) setRefreshing(false)
      }
    },
    [session, classroom?.class_id],
  )

  useEffect(() => {
    if (session) void reload().catch(fail)
  }, [session]) // reload once per authenticated session

  async function action(operation: () => Promise<void>) {
    if (busy) return
    setBusy(true)
    setError("")
    setNotice("")
    try {
      await operation()
    } catch (reason) {
      fail(reason)
    } finally {
      setBusy(false)
    }
  }
  async function preview(command: Command) {
    if (!session) return
    const generation = loading.current
    let proposal: Proposal
    try {
      proposal = await request<Proposal>(`${workspace(session)}/commands/preview`, command, session.csrf_token)
    } catch (reason) {
      if (generation === loading.current && alive.current) throw reason
      return
    }
    if (generation !== loading.current || !alive.current) return
    setPending({ proposal, key: crypto.randomUUID() })
    setForm(null)
    setRecordNoteQuote("")
  }
  async function commit() {
    if (!session || !pending) return
    const generation = loading.current
    const base = `${workspace(session)}/commands`
    let receipt: CommandReceipt
    try {
      let approval = pending.approval
      if (pending.proposal.risk === "W2" && !approval) {
        const response = await request<unknown>(
          `${base}/approve`,
          {
            proposal_id: pending.proposal.proposal_id,
            payload_hash: pending.proposal.payload_hash,
          },
          session.csrf_token,
        )
        if (generation !== loading.current || !alive.current) return
        approval = decodeApproval(response)
        setPending({ ...pending, approval })
      }
      const response = await request<unknown>(
        `${base}/commit`,
        {
          proposal_id: pending.proposal.proposal_id,
          idempotency_key: pending.key,
          approval: approval || null,
        },
        session.csrf_token,
      )
      if (generation !== loading.current || !alive.current) return
      receipt = decodeCommandReceipt(response, pending.proposal.payload)
    } catch (reason) {
      if (generation === loading.current && alive.current) throw reason
      return
    }
    await acceptReceipt(receipt, String(pending.proposal.payload.command))
  }
  async function acceptReceipt(receipt: CommandReceipt, command: string) {
    if (command.startsWith("model_configuration.")) {
      runningAgent.current?.abort(); setConversationId(""); setMessages([]); setMessage(""); setAgentStatus("")
      setModelRevision(value => value + 1)
    }
    if (command === "exit_export.create") setExportId(receipt.resource_id)
    setPending(null)
    setAgentDraft(null)
    setAgentRecordNote(null); setRecordNoteQuote("")
    setDraftTitle("")
    setRecord(null)
    setTask(null)
    setReplacingIdentifier(null)
    setNotice(`已保存，版本 ${receipt.version}；回执 ${receipt.receipt_id}`)
    await reload()
  }
  async function checkCommit() {
    if (!session || !pending) return
    const generation = loading.current
    let result: ReturnType<typeof decodeCommandState>
    try {
      const response = await request<unknown>(`${workspace(session)}/commands/${pending.proposal.proposal_id}/receipts/${pending.key}`)
      if (generation !== loading.current || !alive.current) return
      result = decodeCommandState(response, pending.proposal)
    } catch (reason) {
      if (generation === loading.current && alive.current) throw reason
      return
    }
    if (result.status === "committed" && result.receipt) await acceptReceipt(result.receipt, String(pending.proposal.payload.command))
    else setError(result.status === "not_committed" ? "未查询到原请求键的已提交收据；核对后可按原键重试，不要重复新建。" : "当前预览已失效或无法按原键提交；请核对现有数据，不要盲目重新录入。")
  }
  const editable = !!classroom && classroom.status !== "archived" && !refreshing
  const selected = students.find((item) => item.student_id === selectedStudent)
  const canEditStudent = editable && selected?.status !== "inactive"
  const studentName = (id: string | null) =>
    students.find((item) => item.student_id === id)?.name ||
    (id ? "已停用学生 / 查看历史" : "班级工作")
  const latest = (activity?.records || []).filter(
    (item, index, array) =>
      !array
        .slice(0, index)
        .some((previous) => previous.record_id === item.record_id),
  )
  const records = selectedStudent
    ? latest.filter((item) => item.student_id === selectedStudent)
    : latest
  const tasks = (activity?.tasks || []).filter(
    (item) => !selectedStudent || item.student_id === selectedStudent,
  )
  const openTasks = tasks.filter(
    (item) => !["done", "cancelled"].includes(item.status),
  )

  function open(next: Form) {
    termLoad.current++
    setTermMetadata(null)
    setError("")
    if (next === "record") setRecordNoteQuote("")
    if (next !== "identifier-edit") setReplacingIdentifier(null)
    setForm(next)
  }
  async function openTerm() {
    if (!session || !classroom) return
    const generation = loading.current, requestId = ++termLoad.current
    setTermMetadata(null)
    try {
      const result = await request<unknown>(`${scope(session, classroom)}/metadata`)
      if (generation !== loading.current || requestId !== termLoad.current || !alive.current) return
      const metadata = decodeTermMetadata(result, classroom)
      setTermMetadata(metadata)
      setForm("term-edit")
    } catch (reason) {
      if (generation === loading.current && requestId === termLoad.current && alive.current) throw reason
    }
  }
  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    const value = (field: string) => String(values.get(field) || "").trim()
    const dateTime = (field: string, known?: string | null) =>
      value(field) ? localDateTimeToUtc(value(field), undefined, known ?? undefined) : null
    const current = classroom
      ? { class_id: classroom.class_id, term_id: classroom.term_id }
      : { class_id: "", term_id: "" }
    void action(async () => {
      if (form === "reauth" || form === "reissue" || form === "logout-all") {
        if (!session) throw new Error("请先登录")
        loading.current++
        runningAgent.current?.abort()
        const path = form === "reauth" ? "reauthenticate" : form === "reissue" ? "recovery/reissue" : "logout-all"
        const response = form === "logout-all"
          ? await identityRequest("signedOut", `/api/identity/${path}`, { password: String(values.get("password") || "") }, session.csrf_token)
          : form === "reissue"
            ? await identityRequest("kit", `/api/identity/${path}`, { password: String(values.get("password") || "") }, session.csrf_token)
            : await identityRequest("session", `/api/identity/${path}`, { password: String(values.get("password") || "") }, session.csrf_token)
        runningAgent.current?.abort(); loading.current++
        setPending(null); setForm(null); setReplacingIdentifier(null); setMessages([]); setMessage(""); setConversationId("")
        setAgentDraft(null); setAgentRecordNote(null); setRecordNoteQuote(""); setAgentStatus(""); setDraftTitle(""); setExportId("")
        if (form === "logout-all") {
          setPage("conversation"); setSelectedStudent(""); setRecord(null); setTask(null)
          setSession(null); setStudents([]); setActivity(null); setClasses([]); setClassroom(null)
          setIdentifiers([]); setDuplicates([]); setIssuedCodes(null)
        } else {
          if (!("subject" in response)) throw new IdentityOutcomeUnknown()
          const codes = "recovery_codes" in response && Array.isArray(response.recovery_codes) ? response.recovery_codes as string[] : undefined
          const clean = { schema_version: response.schema_version, csrf_token: response.csrf_token, subject: response.subject }
          setSession(clean)
          if (form === "reissue") setIssuedCodes(codes || [])
          setNotice("身份已确认，会话已旋转；旧会话绑定的草稿与批准失效。")
        }
        return
      }
      let command: Command
      if (form === "class")
        command = {
          command: "class.create",
          class_id: crypto.randomUUID(),
          term_id: crypto.randomUUID(),
          name: value("name"),
          term_name: value("term_name"),
          start_date: value("start"),
          end_date: value("end"),
        }
      else if (!classroom) throw new Error("请先建立班级")
      else if (form === "class-edit")
        command = {
          command: "class.update",
          ...current,
          expected_version: classroom.version,
          name: value("name"),
        }
      else if (form === "student")
        command = {
          command: "student.create",
          ...current,
          student_id: crypto.randomUUID(),
          expected_class_version: classroom.version,
          name: value("name"),
        }
      else if (form === "term-edit" && termMetadata
        && termMetadata.class_id === classroom.class_id && termMetadata.term_id === classroom.term_id)
        command = {
          command: "term.update", ...current, expected_version: termMetadata.version,
          previous_name: termMetadata.name, name: value("term_name"),
          previous_start_date: termMetadata.start_date, start_date: value("start"),
          previous_end_date: termMetadata.end_date, end_date: value("end"),
        }
      else if (form === "student-name" && selected)
        command = {
          command: "student.update_name",
          ...current,
          student_id: selected.student_id,
          expected_version: selected.version,
          previous_name: selected.name,
          name: value("name"),
        }
      else if (form === "record")
        command = {
          command: "record.create",
          ...current,
          record_id: crypto.randomUUID(),
          student_id: value("student"),
          kind: value("kind"),
          occurred_at: dateTime("occurred"),
          fact_text: value("fact"),
          observation_text: value("observation"),
          related_record_id: value("related") || null,
        }
      else if (form === "task")
        command = {
          command: "task.create",
          ...current,
          task_id: crypto.randomUUID(),
          title: value("title"),
          due_at: dateTime("due"),
          student_id: value("student") || null,
          source_record_id: value("source") || null,
        }
      else if ((form === "identifier" || form === "identifier-edit") && selected)
        command = {
          command: "student.update_identifier",
          ...current,
          student_id: selected.student_id,
          identifier_id: crypto.randomUUID(),
          expected_version: selected.version,
          authority: form === "identifier-edit" ? replacingIdentifier?.authority || "" : value("authority"),
          identifier_type: form === "identifier-edit" ? replacingIdentifier?.identifier_type || "" : value("type"),
          value: value("value"),
          valid_from: dateTime("start"),
          valid_to: dateTime("end"),
          ...(form === "identifier-edit" ? { supersedes_identifier_id: replacingIdentifier?.identifier_id || "" } : {}),
        }
      else if (form === "revise" && record)
        command = {
          command: "record.correct",
          ...current,
          record_id: record.record_id,
          expected_version: record.version,
          fact_text: value("fact"),
          observation_text: value("observation"),
          reason: value("reason"),
        }
      else if (form === "task-edit" && task) {
        const due = dateTime("due", task.due_at)
        const changed = due === null ? task.due_at !== null : task.due_at === null || Date.parse(due) !== Date.parse(task.due_at)
        command = { command: "task.update", ...current, task_id: task.task_id, expected_version: task.version,
                    status: task.status, evidence: task.evidence, title: value("title"),
                    ...(changed ? { change_due_date: true, due_at: due } : {}) }
      }
      else if ((form === "complete" || form === "cancel") && task)
        command = {
          command: form === "complete" ? "task.complete" : "task.cancel",
          ...current,
          task_id: task.task_id,
          expected_version: task.version,
          status: form === "complete" ? "done" : "cancelled",
          evidence: value("evidence"),
        }
      else throw new Error("请重新选择操作对象")
      await preview(command)
    })
  }

  const selectedAgentStudent = students.find(item => item.student_id === agentStudent && item.status === "active")
  const agentScopeUnavailable = Boolean(agentStudent) && !selectedAgentStudent
  async function changeAgentContext(studentId: string, mode = agentMode) {
    if (!session || busy || refreshing || runningAgent.current) return
    const generation = loading.current
    await action(async () => {
      if (conversationId) {
        try { await request(`${workspace(session)}/agent/conversations/${conversationId}/forget`, {}, session.csrf_token) }
        catch (reason) {
          if (generation !== loading.current || !alive.current) return
          if (!(reason instanceof ApiError && reason.status === 409)) throw reason
        }
      }
      if (generation !== loading.current || !alive.current) return
      setAgentStudent(studentId); setAgentMode(mode); setConversationId("")
      setMessages([]); setAgentDraft(null); setAgentRecordNote(null); setRecordNoteQuote(""); setAgentStatus("")
      setNotice("助理范围已切换，旧对话已清理；未发送文字保留。仅影响对话，不修改班级或学生事实。")
    })
  }
  async function sendMessage() {
    if (!session || !classroom || !editable || busy || refreshing || !message.trim() || runningAgent.current || modelUncertain || agentScopeUnavailable) return
    const controller = new AbortController()
    runningAgent.current = controller
    const text = message.trim()
    followingConversation.current = true; setNewReply(false)
    setMessage(""); setError(""); setAgentDraft(null); setAgentRecordNote(null); setAgentStatus("连接 Agent…")
    setMessages(previous => [...previous, { role: "user", text }])
    let answer = "", draft: string | null = null, failed = false
    let noteDraft: unknown = null
    let sources: QuerySource[] = []
    try {
      let conversation = conversationId
      if (!conversation) {
        const created = await createScopedConversation(session, classroom, agentStudent || null, controller.signal)
        if (controller.signal.aborted) return
        conversation = created.conversation_id; setConversationId(conversation)
      }
      const recordNoteMode = agentMode === "record-note"
      const body = recordNoteMode
        ? { schema_version: "class-os.agent-record-note-request.v1", conversation_id: conversation, text }
        : { conversation_id: conversation, text, mode: agentMode }
      const response = await fetch(`${workspace(session)}/agent/${recordNoteMode ? "record-note/events" : "events"}`, { method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: { "content-type": "application/json", "x-class-os-csrf": session.csrf_token },
        body: JSON.stringify(body) })
      if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
      await consumeEvents(response, event => {
        if (controller.signal.aborted) return
        if (event.type === "run.started") setAgentStatus(event.payload.provider === "configured-api" ? "Agent 已开始（已配置 API）" : "Agent 已开始（离线合成或协议测试）")
        if (event.type === "tool.started") setAgentStatus(event.payload.tool === "attention_list" ? "正在查询当前工作…" : "正在整理未提交草稿…")
        if (event.type === "draft.available") {
          const candidate = event.payload.draft
          if (recordNoteMode) noteDraft = candidate
          else if (candidate && typeof candidate === "object" && "title" in candidate && typeof candidate.title === "string") draft = candidate.title
        }
        if (event.type === "message.delta" && typeof event.payload.text === "string") {
          answer = event.payload.text
          const refs = event.payload.source_refs
          if (!Array.isArray(refs)) throw new Error("缺少受控来源字段")
          sources = refs.map(item => {
            if (!item || Object.keys(item).sort().join(",") !== "as_of,entity,id,projection_hash,version"
              || item.entity !== "query_receipt" || typeof item.id !== "string" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(item.id)
              || item.version !== 1 || typeof item.projection_hash !== "string" || !/^[a-f0-9]{64}$/.test(item.projection_hash)
              || typeof item.as_of !== "string" || !Number.isFinite(Date.parse(item.as_of))) throw new Error("查询来源校验失败，未采纳答案")
            return item as QuerySource
          })
          if (agentMode === "read" && sources.length !== 1) throw new Error("当前工作答案缺少真实查询回执")
        }
        if (event.type === "run.failed") failed = true
      })
      if (failed || !answer || controller.signal.aborted) throw new Error("Agent 未完成，未采纳草稿或写入业务事实。")
      const recordNote = recordNoteMode ? await parseRecordNoteCandidate(noteDraft, text, controller.signal) : null
      if (controller.signal.aborted) return
      setMessages(previous => [...previous, { role: "assistant", text: answer, sources }]); setAgentDraft(draft); setAgentRecordNote(recordNote)
      setAgentStatus("已完成 · 无业务写入")
    } catch (reason) {
      if (controller.signal.aborted) setAgentStatus("已停止 · 未采纳未完成结果")
      else { fail(reason); setAgentStatus("运行未完成"); if (reason instanceof ApiError && reason.status === 409) setConversationId("") }
    } finally { if (runningAgent.current === controller) runningAgent.current = null }
  }

  if (checking)
    return (
      <div className="r1-auth">
        <p role="status">正在检查本地会话…</p>
      </div>
    )
  if (!session)
    return (
      <Login error={error} busy={busy} onError={fail} onSession={value => { setError(""); setSession(value) }}
        onProbeSession={value => { setError(""); setNotice("登录状态已只读核对；没有重新执行前次身份操作，也不据此判定它已经完成。"); setSession(value) }} />
    )

  const taskCards = (items: TaskItem[]) =>
    items.length ? (
      items.map((item) => (
        <button
          key={item.task_id}
          className="r1-attention-item"
          onClick={() => {
            setTask(item)
            setPage("work")
          }}
        >
          <span>
            {item.title}
            <small>
              {item.overdue ? "已逾期 · " : ""}
              {displayTime(item.due_at)}
            </small>
          </span>
          <span>›</span>
        </button>
      ))
    ) : (
      <p className="r1-muted">暂无事项</p>
    )
  return (
    <div className="r1-shell">
      <aside className="r1-sidebar">
        <h2>
          ClassMatter <small>合成开发</small>
        </h2>
        <button
          className="r1-new"
          disabled={busy || !!runningAgent.current}
          onClick={() => void action(async () => {
            const generation = loading.current
            if (conversationId) {
              try { await request(`${workspace(session)}/agent/conversations/${conversationId}/forget`, {}, session.csrf_token) }
              catch (reason) {
                if (generation !== loading.current || !alive.current) return
                if (!(reason instanceof ApiError && reason.status === 409)) throw reason
              }
            }
            if (generation !== loading.current || !alive.current) return
            setConversationId("")
            setAgentDraft(null)
            setAgentRecordNote(null); setRecordNoteQuote("")
            setAgentStatus("")
            setMessages([])
            setMessage("")
            setPage("conversation")
          })}
        >
          <Plus size={17} />
          新对话
        </button>
        <nav>
          {([
            ["conversation", "对话", MessageSquare],
            ["dashboard", "总览", LayoutDashboard],
            ["students", "学生", Users],
            ["work", "工作", ClipboardList],
            ["settings", "设置", Settings],
          ] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              aria-current={page === id ? "page" : undefined}
              onClick={() => {
                termLoad.current++
                setTermMetadata(null)
                setPage(id)
                setTask(null)
              }}
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
        </nav>
        <section className="r1-scope">
          <label>
            当前班级 / 学期
            <select
              aria-label="切换班级学期"
              value={classroom?.class_id || ""}
              onChange={(event) => {
                const target = classes.find(
                  (item) => item.class_id === event.target.value,
                )
                setSelectedStudent("")
                void action(() => reload(target || null))
              }}
            >
              <option value="" disabled>
                尚未建立
              </option>
              {classes.map((item) => (
                <option key={item.class_id} value={item.class_id}>
                  {item.name} · {item.term_name}
                  {item.status === "archived" ? "（归档只读）" : ""}
                </option>
              ))}
            </select>
          </label>
          {!classes.some((item) => item.status === "active") && (
            <button disabled={busy || refreshing} onClick={() => open("class")}>建立班级与学期</button>
          )}
        </section>
        <div className="r1-future">
          <small>后续版本</small>
          <p>通知与责任候选 · 文件与语音 · 知识库 · 自动化</p>
          <span>尚未启用，不作假成功演示</span>
        </div>
        <button
          className="r1-logout"
          disabled={busy}
          onClick={() =>
            void action(async () => {
              await logoutIdentity(session.csrf_token)
              loading.current++
              setSession(null)
              setPage("conversation")
              setSelectedStudent("")
              setRecord(null)
              setTask(null)
              setStudents([])
              setActivity(null)
              setClasses([])
              setClassroom(null)
              setIdentifiers([])
              setReplacingIdentifier(null)
              setDuplicates([])
              setMessages([])
              setPending(null)
              setForm(null)
              setIssuedCodes(null)
              setExportId("")
            })
          }
        >
          <LogOut size={16} />
          退出登录
        </button>
      </aside>
      <main className="r1-main">
        <header className="r1-topbar">
          <strong>{classroom?.name || "班事有谱"}</strong>
          <span role={refreshing ? "status" : undefined}>
            {refreshing ? "正在读取当前班级与学期…" : classroom?.term_name || "先建立班级与学期"}
            {classroom?.status === "archived" && " · 历史只读"}
          </span>
          <button
            aria-label="刷新数据"
            disabled={busy || refreshing}
            onClick={() => void action(() => reload())}
          >
            <RefreshCw size={16} />
          </button>
        </header>
        {error && !form && !pending && (
          <div className="r1-error" role="alert">
            {error}
            <button onClick={() => setError("")} aria-label="关闭错误">
              <X size={14} />
            </button>
          </div>
        )}
        {notice && (
          <div className="r1-notice" role="status">
            {notice}
          </div>
        )}
        <div ref={conversationViewport} className={`r1-scroll${page === "conversation" ? " r1-conversation-scroll" : ""}`} onScroll={event => {
          if (page !== "conversation") return
          const viewport = event.currentTarget
          followingConversation.current = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop <= 48
          if (followingConversation.current) setNewReply(false)
        }}>
          {page === "conversation" && (
            <>
              <div className="r1-heading">
                <small>CLASSMATTER · 对话</small>
                <h1>今天想处理什么？</h1>
                <p>少记、少追、少重复。事实由你确认，系统帮你复用。</p>
              </div>
              <div className="r1-attention">
                <section>
                  <h3>需要我处理</h3>
                  {taskCards(
                    openTasks.filter((item) => item.status !== "waiting"),
                  )}
                </section>
                <section>
                  <h3>可能遗漏</h3>
                  <p className="r1-muted">
                    R1 暂无通知责任候选。系统不依据 AI 推断自动判责。
                  </p>
                  {duplicates.length > 0 && (
                    <button onClick={() => setPage("students")}>
                      {duplicates.length} 组标识重复候选待核对
                    </button>
                  )}
                </section>
                <section>
                  <h3>等待别人</h3>
                  {taskCards(
                    openTasks.filter((item) => item.status === "waiting"),
                  )}
                </section>
              </div>
              <div className="r1-quick">
                <button
                  disabled={!classroom || !editable || !students.length}
                  onClick={() => {
                    setRecord(null)
                    open("record")
                  }}
                >
                  记录事实
                </button>
                <button
                  disabled={!classroom || !editable}
                  onClick={() => {
                    setRecord(null)
                    open("task")
                  }}
                >
                  建立跟进
                </button>
                <button onClick={() => setPage("students")}>查看学生</button>
              </div>
              <div ref={conversationContent} className="r1-messages">
                {agentMode === "read" && <p className="r1-muted">助理查询范围：{agentStudent ? selectedAgentStudent?.name || "已选学生不可用，请重新选择；不会回落全班" : "全班当前工作"}。仅统计，不作评价。</p>}
                {messages.map((item, i) => (
                  <article key={i} className={item.role}>
                    <small>{item.role === "user" ? "你" : "ClassMatter"}</small>
                    <p>{item.text}</p>
                    {item.sources?.map(source => <details key={source.id} className="r1-muted"><summary>已审计的当前工作快照 · {displayTime(source.as_of)}</summary><p>查询回执：{source.id}</p><p>完整来源版本摘要：{source.projection_hash}</p><small>这是一轮只读查询的来源证明，不是记忆中的事实或写入批准。</small></details>)}
                  </article>
                ))}
                {agentStatus && <p role="status" className="r1-muted">{agentStatus}</p>}
                {agentDraft && <section className="r1-card"><h2>未提交的任务草稿</h2><p>{agentDraft}</p><p className="r1-muted">尚未保存。只有你核对表单、预览并明确提交，才会成为业务数据。</p><button onClick={() => { setDraftTitle(agentDraft); setRecord(null); open("task") }}>打开草稿并核对</button><button onClick={() => setAgentDraft(null)}>放弃草稿</button></section>}
                {agentRecordNote && <section className="r1-card"><h2>待核对的原文草稿</h2><p>{agentRecordNote.note_quote}</p><p className="r1-warning">仅摘录你本轮的原文，不证明内容真实，尚未保存；学生、类型和发生时间都需要你明确核对，不能把猜测当事实。</p><button onClick={() => { setRecord(null); open("record"); setRecordNoteQuote(agentRecordNote.note_quote) }}>打开原文草稿并核对</button><button onClick={() => setAgentRecordNote(null)}>放弃原文草稿</button></section>}
              </div>
            </>
          )}
          {page === "dashboard" && (
            <>
              <div className="r1-heading">
                <h1>今天的班级工作</h1>
                <p>
                  来自同一数据世界 · 查询时间{" "}
                  {activity ? displayTime(activity.as_of) : "尚无数据"}
                </p>
              </div>
              <div className="r1-stats">
                <button onClick={() => setPage("students")}>
                  {students.length}
                  <span>学生</span>
                </button>
                <button onClick={() => setPage("work")}>
                  {openTasks.length}
                  <span>未结束任务</span>
                </button>
                <button onClick={() => setPage("students")}>
                  {latest.length}
                  <span>已确认事实 / 观察</span>
                </button>
              </div>
              <h2>任务</h2>
              {taskCards(openTasks)}
              <h2>最近事实</h2>
              {records.slice(0, 10).map((item) => (
                <RecordCard
                  key={item.record_id}
                  item={item}
                  name={studentName(item.student_id)}
                  editable={editable}
                  canCreateTask={editable && students.some(student => student.student_id === item.student_id && student.status !== "inactive")}
                  onCorrect={() => {
                    setRecord(item)
                    open("revise")
                  }}
                  onTask={() => {
                    setRecord(item)
                    open("task")
                  }}
                />
              ))}
            </>
          )}
          {page === "students" && (
            <>
              <div className="r1-heading">
                <h1>{selected ? selected.name : "学生"}</h1>
                <p>姓名不是唯一身份，关联使用稳定 ID。</p>
              </div>
              <div className="r1-toolbar">
                <input
                  aria-label="搜索学生"
                  placeholder="搜索学生"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <button
                  disabled={!classroom || !editable}
                  onClick={() => open("student")}
                >
                  添加学生
                </button>
                {selected && (
                  <button onClick={() => setSelectedStudent("")}>
                    返回全部学生
                  </button>
                )}
              </div>
              {!classroom ? (
                <p>请先建立班级与学期。</p>
              ) : (
                <div className="r1-student-layout">
                  <div className="r1-student-list">
                    {students
                      .filter((item) => item.name.includes(search))
                      .map((item) => (
                        <button
                          key={item.student_id}
                          aria-pressed={selectedStudent === item.student_id}
                          onClick={() => {
                            setSelectedStudent(item.student_id)
                            setRecord(null)
                          }}
                        >
                          <strong>{item.name}</strong>
                          <small>
                            版本 {item.version} · {item.student_id.slice(0, 8)}
                            {item.status === "inactive" ? " · 已停用（历史可查）" : ""}
                          </small>
                        </button>
                      ))}
                    {!students.length && (
                      <p className="r1-muted">尚无学生，添加后即可记录事实。</p>
                    )}
                  </div>
                  <section>
                    {selected && (
                      <div className="r1-toolbar">
                        <button disabled={!canEditStudent || busy} onClick={() => open("student-name")}>
                          更正学生姓名
                        </button>
                        <button
                          disabled={!canEditStudent || busy}
                          onClick={() => {
                            setRecord(null)
                            open("record")
                          }}
                        >
                          记录事实
                        </button>
                        <button
                          disabled={!canEditStudent || busy}
                          onClick={() => {
                            setRecord(null)
                            open("task")
                          }}
                        >
                          建立跟进
                        </button>
                        <button
                          disabled={!canEditStudent || busy}
                          onClick={() => open("identifier")}
                        >
                          添加来源标识
                        </button>
                        <button
                          disabled={!canEditStudent || busy}
                          onClick={() =>
                            void action(() =>
                              preview({
                                command: "student.deactivate",
                                class_id: classroom.class_id,
                                term_id: classroom.term_id,
                                student_id: selected.student_id,
                                expected_version: selected.version,
                              }),
                            )
                          }
                        >
                          停用（保留历史）
                        </button>
                      </div>
                    )}
                    {selected &&
                      identifiers
                        .filter(
                          (item) => item.student_id === selected.student_id,
                        )
                        .map((item) => (
                          <div className="r1-muted" key={item.identifier_id}>
                            {item.authority} · {item.identifier_type} ·{" "}
                            {item.value} · {displayTime(item.valid_from)}—
                            {item.valid_to
                              ? displayTime(item.valid_to)
                              : "长期有效"}
                            {item.valid_to === null && <button disabled={!canEditStudent || busy} aria-label={`更正来源标识 ${item.value}`} onClick={() => { setReplacingIdentifier(item); open("identifier-edit") }}>更正（保留旧值）</button>}
                          </div>
                        ))}
                    {duplicates.map((item) => (
                      <div
                        className="r1-warning"
                        key={item.left_student_id + item.right_student_id}
                      >
                        {studentName(item.left_student_id)} 与{" "}
                        {studentName(item.right_student_id)}{" "}
                        有标识重复候选。保持独立，不自动合并。
                      </div>
                    ))}
                    <h2>事实时间线</h2>
                    {records.length ? (
                      records.map((item) => (
                        <RecordCard
                          key={item.record_id}
                          item={item}
                          name={studentName(item.student_id)}
                          editable={editable}
                          canCreateTask={editable && students.some(student => student.student_id === item.student_id && student.status !== "inactive")}
                          onCorrect={() => {
                            setRecord(item)
                            open("revise")
                          }}
                          onTask={() => {
                            setRecord(item)
                            open("task")
                          }}
                        />
                      ))
                    ) : (
                      <p className="r1-muted">尚无已确认事实。</p>
                    )}
                  </section>
                </div>
              )}
            </>
          )}
          {page === "work" && (
            <>
              <div className="r1-heading">
                <h1>工作与跟进</h1>
                <p>个人工作状态不代表学校授权或他人已接受交接。</p>
              </div>
              <div className="r1-toolbar">
                <button
                  disabled={!classroom || !editable}
                  onClick={() => {
                    setRecord(null)
                    open("task")
                  }}
                >
                  新建任务
                </button>
                <select
                  aria-label="按学生筛选任务"
                  value={selectedStudent}
                  onChange={(event) => setSelectedStudent(event.target.value)}
                >
                  <option value="">全部学生 / 班级</option>
                  {students.map((item) => (
                    <option key={item.student_id} value={item.student_id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </div>
              {!tasks.length && <p className="r1-muted">尚无任务。</p>}
              {tasks.map((item) => (
                <article className="r1-card" key={item.task_id}>
                  <button
                    className="r1-task-title"
                    onClick={() =>
                      setTask(task?.task_id === item.task_id ? null : item)
                    }
                  >
                    <strong>{item.title}</strong>
                    <span>
                      {states[item.status]}
                      {item.overdue ? " · 已逾期" : ""}
                    </span>
                  </button>
                  <p>
                    {studentName(item.student_id)} · {displayTime(item.due_at)}{" "}
                    · v{item.version}
                  </p>
                  {item.source_record_id && (
                    <details>
                      <summary>查看来源事实与历史</summary>
                      <p className="r1-muted">关联记录，不锁定建立任务时的版本；以下显示当前事实及历史更正。</p>
                      {(activity?.records || []).some(source => source.record_id === item.source_record_id) ?
                        (activity?.records || []).filter(source => source.record_id === item.source_record_id).map(source => (
                          <article className="r1-card" key={`${source.record_id}-${source.version}`}>
                            <strong>{studentName(source.student_id)} · {kinds[source.kind] || source.kind} · v{source.version}</strong>
                            {source.fact_text && <p>事实：{source.fact_text}</p>}
                            {source.observation_text && <p>教师观察：{source.observation_text}</p>}
                            <small>发生 {displayTime(source.occurred_at)} · 记录 {displayTime(source.recorded_at)}</small>
                            {source.revision_reason && <p>更正理由：{source.revision_reason}</p>}
                          </article>
                        )) : <p>当前查询中来源不可用；请刷新后核对，不据此推断事实。</p>}
                    </details>
                  )}
                  {item.evidence && <p>结果：{item.evidence}</p>}
                  {task?.task_id === item.task_id &&
                    editable &&
                    !["done", "cancelled"].includes(item.status) && (
                      <div className="r1-toolbar">
                        <button disabled={busy} onClick={() => open("task-edit")}>编辑标题与截止时间</button>
                        {(["in-progress", "waiting", "not-started"] as const)
                          .filter((status) => status !== item.status)
                          .map((status) => (
                            <button
                              disabled={busy}
                              key={status}
                              onClick={() =>
                                void action(() =>
                                  preview({
                                    command: "task.update",
                                    class_id: classroom!.class_id,
                                    term_id: classroom!.term_id,
                                    task_id: item.task_id,
                                    expected_version: item.version,
                                    status,
                                    evidence: "",
                                  }),
                                )
                              }
                            >
                              {states[status]}
                            </button>
                          ))}
                        <button onClick={() => open("complete")}>
                          完成并记结果
                        </button>
                        <button onClick={() => open("cancel")}>
                          取消并记原因
                        </button>
                      </div>
                    )}
                </article>
              ))}
            </>
          )}
          {page === "settings" && (
            <>
              <div className="r1-heading">
                <h1>设置与数据</h1>
                <p>本地合成开发模式 · 不能接入真实学生数据。</p>
              </div>
              <section className="r1-card">
                <h2>当前班级与学期</h2>
                <button disabled={!classroom || busy || refreshing} onClick={event => { auditOpener.current = event.currentTarget; void action(async () => {
                  if (!classroom) return
                  const generation = loading.current
                  try {
                    const result = await request<AuditPage>(`${scope(session, classroom)}/audit`)
                    if (generation === loading.current && alive.current) setAuditPage(result)
                  } catch (reason) {
                    if (generation === loading.current && alive.current) throw reason
                  }
                }) }}>查看班级业务审计</button>
                {!classes.some(item => item.status === "active") && <button disabled={busy || refreshing} onClick={() => open("class")}>建立班级与学期</button>}
                <label>切换查看班级<select aria-label="设置中切换班级" value={classroom?.class_id || ""} onChange={event => {
                  const target = classes.find(item => item.class_id === event.target.value)
                  setSelectedStudent("")
                  void action(() => reload(target || null))
                }}><option value="" disabled>尚未建立</option>{classes.map(item => <option value={item.class_id} key={item.class_id}>{item.name} · {item.term_name}{item.status === "archived" ? "（归档只读）" : ""}</option>)}</select></label>
                <p>
                  {classroom
                    ? `${classroom.name} · ${classroom.term_name}`
                    : "尚未建立"}
                </p>
                {classroom && editable && (
                  <button disabled={busy} onClick={() => open("class-edit")}>编辑班级名称</button>
                )}
                {classroom && editable && (
                  <button disabled={busy || refreshing} onClick={() => void action(openTerm)}>更正学期信息</button>
                )}
                {classroom && editable && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action(() =>
                        preview({
                          command: "class.archive",
                          class_id: classroom.class_id,
                          term_id: classroom.term_id,
                          expected_version: classroom.version,
                          name: classroom.name,
                        }),
                      )
                    }
                  >
                    预览归档（历史仍可查看）
                  </button>
                )}
              </section>
              <section className="r1-card">
                <h2>可替换 AI 能力</h2>
                <p>
                  默认使用离线合成模型。仅在显式允许地址、测试通过并启用后调用配置 API；模型不会直接拥有数据库写入或批准权限。
                </p>
                <ModelConfigurationForm key={`${session.csrf_token}/${modelRevision}`} session={session} disabled={busy} onError={fail}
                  onPreview={command => action(() => preview(command))} onModeChanged={verified => {
                    setModelUncertain(!verified)
                    runningAgent.current?.abort(); setConversationId(""); setMessages([]); setMessage(""); setAgentDraft(null); setAgentRecordNote(null); setRecordNoteQuote(""); setAgentStatus("")
                    setNotice(verified ? "模型运行状态已核对，旧对话视图已清理；业务数据未变。" : "模型状态待核对，暂不发送新的 Agent 消息；直接业务 UI 仍可使用。")
                  }} />
                <p className="r1-muted">
                  文件、语音、微信、长记忆和自动化均不在 R1 实现范围。
                </p>
              </section>
              <section className="r1-card"><h2>身份与恢复</h2><p>这些操作需要当前密码，不经 Agent。重新签发会撤销旧恢复码和全部旧会话；全部设备退出不改变密码。</p><div className="r1-toolbar"><button disabled={busy} onClick={() => open("reauth")}>重新验证身份</button><button disabled={busy} onClick={() => open("reissue")}>重新签发离线恢复码</button><button disabled={busy} onClick={() => open("logout-all")}>注销全部设备</button></div></section>
              <section className="r1-card">
                <h2>退出导出</h2>
                <p>当前可导出完整合成核心数据与历史版本；不含密码、会话和批准凭据。生命周期台账、退役证明与干净恢复仍在开发，不能将本包当作正式完整退出证明。</p>
                <button disabled={busy} onClick={() => void action(async () => {
                  const summary = await request<{ core_hash: string }>(`${workspace(session)}/exit/summary`)
                  await preview({ command: "exit_export.create", export_id: crypto.randomUUID(), expected_core_hash: summary.core_hash })
                })}>生成合成核心退出包</button>
                {exportId && <p><a href={`${workspace(session)}/exit/${exportId}/download`} download>下载已批准的核心包（30分钟内）</a></p>}
              </section>
              <button disabled={busy} onClick={() => void action(async () => {
                await logoutIdentity(session.csrf_token)
                loading.current++
                setPage("conversation"); setSelectedStudent(""); setRecord(null); setTask(null)
                setSession(null); setStudents([]); setActivity(null); setClasses([]); setClassroom(null)
                setIdentifiers([]); setReplacingIdentifier(null); setDuplicates([]); setMessages([]); setPending(null); setForm(null); setIssuedCodes(null); setExportId("")
              })}>注销当前会话</button>
            </>
          )}
        </div>
        {page === "conversation" && newReply && <button className="r1-new-reply" type="button" onClick={() => {
          followingConversation.current = true
          scrollToLatest()
          messageInput.current?.focus({ preventScroll: true })
        }}>查看新回复</button>}
        {page === "conversation" && (
          <form
            className="r1-composer"
            onSubmit={(event) => {
              event.preventDefault()
              void sendMessage()
            }}
          >
            <textarea
              ref={messageInput}
              aria-label="输入消息"
              placeholder="输入、查询、记录或安排班级工作……"
              value={message}
              maxLength={2000}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault()
                  void sendMessage()
                }
              }}
            />
            <div>
              <span className="r1-muted">
                附件 / 语音：后续版本 · 当前仅文字
              </span>
              <label>班级助理<select aria-label="Agent 交互模式" value={agentMode} disabled={busy || refreshing || !!runningAgent.current} onChange={event => void changeAgentContext("", event.target.value as AgentInteraction)}><option value="read">查询当前工作</option><option value="draft">仅生成任务草稿</option><option value="record-note">整理记录原文草稿</option><option value="chat">讨论，不调用工具</option></select></label>
              {agentMode === "read" && <label className="r1-agent-scope">查询范围<select aria-label="助理查询范围" value={agentStudent} disabled={busy || refreshing || !!runningAgent.current} onChange={event => void changeAgentContext(event.target.value)}>
                <option value="">全班当前工作</option>
                {agentScopeUnavailable && <option value={agentStudent} disabled>已选学生不可用，请重新选择</option>}
                {students.filter(item => item.status === "active").map(item => <option key={item.student_id} value={item.student_id}>{item.name} · 个人跟进</option>)}
              </select></label>}
              {runningAgent.current ? <button type="button" aria-label="停止 Agent" onClick={() => runningAgent.current?.abort()}><X size={18} /></button> : <button aria-label="发送消息" disabled={!message.trim() || busy || refreshing || !classroom || !editable || modelUncertain || agentScopeUnavailable}>
                <ArrowUp size={18} />
              </button>}
            </div>
          </form>
        )}
      </main>
      {auditPage && <R1Dialog titleId="r1-audit-title" returnFocusTo={auditOpener.current} onDismiss={() => setAuditPage(null)}>
        <h2 id="r1-audit-title">班级业务审计 · 只读摘要</h2>
        <p>当前 owner / 班级 / 学期范围的最近100条登记。较早未登记范围的操作不在此视图，不代表没有发生。</p>
        <p className="r1-muted">查询时间 {displayTime(auditPage.as_of)}；{auditPage.truncated ? "还有更早登记未展示。" : "本次范围内登记已展示。"}不含会话、密码或事实原文。</p>
        <button onClick={() => setAuditPage(null)}>关闭审计摘要</button>
        {auditPage.entries.map(entry => <article className="r1-card" key={entry.event_id}>
          <strong>{entry.action} · {entry.outcome === "allowed" ? "允许" : "拒绝"}</strong>
          <p>{displayTime(entry.occurred_at)}{entry.resource_version !== null ? ` · 资源版本 ${entry.resource_version}` : ""}</p>
          <details><summary>查看回执与摘要</summary><pre>{JSON.stringify({event_id: entry.event_id, proposal_id: entry.proposal_id, payload_hash: entry.payload_hash, receipt_id: entry.receipt_id, resource_id: entry.resource_id}, null, 2)}</pre></details>
        </article>)}
      </R1Dialog>}
      {form && (
        <R1Dialog titleId="r1-form-title" busy={busy} onDismiss={() => { setForm(null); setRecordNoteQuote("") }}>
          {error && <p className="r1-error" role="alert">{error}</p>}
          <header>
              <h2 id="r1-form-title">
                {
                  {
                    class: "建立班级与学期",
                    "class-edit": "编辑班级名称",
                    "term-edit": "更正学期信息",
                    student: "添加学生",
                    "student-name": "更正学生姓名",
                    record: "记录事实 / 观察",
                    task: "建立手工跟进",
                    "task-edit": "编辑手工跟进",
                    identifier: "添加多来源标识",
                    "identifier-edit": "更正来源标识（保留旧值）",
                    revise: "更正事实（保留历史）",
                    complete: "完成任务",
                    cancel: "取消任务",
                    reauth: "重新验证身份",
                    reissue: "重新签发离线恢复码",
                    "logout-all": "注销全部设备",
                  }[form]
                }
              </h2>
              <button
                disabled={busy}
                aria-label="关闭表单"
                onClick={() => { setForm(null); setRecordNoteQuote("") }}
              >
                <X size={18} />
              </button>
            </header>
            <form onSubmit={submitForm}>
              {(form === "reauth" || form === "reissue" || form === "logout-all") && <><Field label="当前密码（身份验证）" name="password" type="password" maxLength={256} /><p className="r1-muted">明确提交后执行身份操作。{form === "reissue" ? "旧恢复码与所有旧会话将失效，请离线保存仅显示一次的新码。" : form === "logout-all" ? "所有设备将立即退出；密码与未使用恢复码保持有效。" : "当前会话将旋转，旧的未提交草稿/批准失效。"}</p></>}
              {form === "class" && (
                <>
                  <Field label="班级名称" name="name" maxLength={80} />
                  <Field label="学期名称" name="term_name" maxLength={80} />
                  <Field label="学期开始" name="start" type="date" />
                  <Field
                    label="学期结束（不包含该日）"
                    name="end"
                    type="date"
                  />
                </>
              )}
              {form === "student" && (
                <Field
                  label="学生姓名（允许同名，内部 ID 区分）"
                  name="name"
                  maxLength={80}
                />
              )}
              {form === "term-edit" && termMetadata && (
                <><Field label="学期名称" name="term_name" defaultValue={termMetadata.name} maxLength={80} />
                  <Field label="学期开始" name="start" type="date" defaultValue={termMetadata.start_date} />
                  <Field label="学期结束（不包含该日）" name="end" type="date" defaultValue={termMetadata.end_date} />
                  <p className="r1-muted">旧值和学期版本已自动带入。仅更正名称和日期，不改写学生、事实、任务或历史归属，不自动切换学期。核对 W2 预览后明确确认。</p></>
              )}
              {form === "class-edit" && (
                <><Field label="班级名称" name="name" defaultValue={classroom?.name} maxLength={80} /><p className="r1-muted">仅修改当前班级名称；学期、学生、事实和任务仍属于同一数据世界。先核对服务端预览再明确提交。</p></>
              )}
              {form === "student-name" && selected && (
                <><p className="r1-muted">当前姓名：{selected.name} · 学生 ID：{selected.student_id}。仅更正显示姓名，不合并同名学生，不改写历史事实和任务。</p><Field label="更正后的学生姓名" name="name" defaultValue={selected.name} maxLength={80} /><p className="r1-muted">旧姓名和当前版本由名单自动带入。请核对服务端 W2 预览后明确确认。</p></>
              )}
              {form === "task-edit" && task && (
                <><Field label="跟进标题" name="title" defaultValue={task.title} maxLength={80} /><Field label="截止时间（本机时区，清空即移除）" name="due" type="datetime-local" step="0.001" defaultValue={localDateValue(task.due_at)} required={false} /><p className="r1-muted">仅编辑当前开放任务的标题和截止时间；不更改关联学生或来源事实，不自动提醒，不重新打开终结任务。</p></>
              )}
              {(form === "record" || form === "task") && (
                <label>
                  关联学生
                  <select
                    name="student"
                    defaultValue={form === "record" && recordNoteQuote ? "" : record?.student_id || selectedStudent}
                    required={form === "record"}
                  >
                    <option value="">
                      {form === "task" ? "班级任务 / 无关联学生" : "请选择学生"}
                    </option>
                    {students.filter(item => item.status !== "inactive").map((item) => (
                      <option key={item.student_id} value={item.student_id}>
                        {item.name} · {item.student_id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {form === "record" && (
                <>
                  {recordNoteQuote && <p className="r1-warning">这是本轮原文摘录，不是已核实事实。请明确选择学生、类型、发生时间，核对并编辑事实 / 观察，再预览确认；来源匹配不证明内容真实。</p>}
                  <label>
                    事实类型
                    <select name="kind" required defaultValue={recordNoteQuote ? "" : "ordinary_fact"} onChange={event => {
                      if (!recordNoteQuote) return
                      const fact = event.currentTarget.form?.elements.namedItem("fact"), observation = event.currentTarget.form?.elements.namedItem("observation")
                      if (!(fact instanceof HTMLTextAreaElement) || !(observation instanceof HTMLTextAreaElement)) return
                      if (event.target.value === "teacher_observation" && fact.value === recordNoteQuote && !observation.value) { observation.value = recordNoteQuote; fact.value = "" }
                      else if (event.target.value !== "teacher_observation" && observation.value === recordNoteQuote && !fact.value) { fact.value = recordNoteQuote; observation.value = "" }
                    }}>
                      <option value="" disabled>请选择事实 / 观察类型</option>
                      {Object.entries(kinds).map(([id, label]) => (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    label="发生时间（本机时区）"
                    name="occurred"
                    type="datetime-local"
                    defaultValue={recordNoteQuote ? "" : localNow()}
                  />
                  <label>
                    事实原文（观察类型请留空）
                    <textarea name="fact" maxLength={2000} defaultValue={recordNoteQuote} />
                  </label>
                  <label>
                    教师观察（不作为客观事实）
                    <textarea name="observation" maxLength={2000} />
                  </label>
                  <label>
                    关联前序事实（批准 / 销假必选）
                    <select name="related">
                      <option value="">无</option>
                      {latest.map((item) => (
                        <option value={item.record_id} key={item.record_id}>
                          {studentName(item.student_id)} · {kinds[item.kind]} ·{" "}
                          {item.fact_text.slice(0, 25)}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
              {form === "task" && (
                <>
                  <Field label="跟进标题" name="title" maxLength={80} defaultValue={draftTitle} />
                  <Field
                    label="截止时间（可不填，本机时区）"
                    name="due"
                    type="datetime-local"
                    required={false}
                  />
                  <label>
                    来源事实
                    <select
                      name="source"
                      defaultValue={record?.record_id || ""}
                    >
                      <option value="">手工任务 / 无来源事实</option>
                      {latest.map((item) => (
                        <option value={item.record_id} key={item.record_id}>
                          {studentName(item.student_id)} · {kinds[item.kind]} ·
                          v{item.version}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
              {(form === "identifier" || form === "identifier-edit") && (
                <>
                  {replacingIdentifier && <p className="r1-muted">旧值：{replacingIdentifier.value}。在下方生效时间结束旧区间，新增替代标识，不覆盖旧值或合并学生。</p>}
                  <Field label="标识签发来源" name="authority" maxLength={80} defaultValue={replacingIdentifier?.authority} readOnly={form === "identifier-edit"} />
                  <label>
                    标识类型
                    <select name="type" defaultValue={replacingIdentifier?.identifier_type || "school_number"} disabled={form === "identifier-edit"}>
                      <option value="school_number">学号</option>
                      <option value="exam_number">考号</option>
                    </select>
                  </label>
                  <Field label="标识值" name="value" maxLength={80} defaultValue={replacingIdentifier?.value} />
                  <Field
                    label="生效时间"
                    name="start"
                    type="datetime-local"
                    defaultValue={localPreciseNow()}
                    step="0.001"
                  />
                  <Field
                    label="失效时间（可不填）"
                    name="end"
                    type="datetime-local"
                    step="0.001"
                    required={false}
                  />
                </>
              )}
              {form === "revise" && record && (
                <>
                  <label>
                    事实原文
                    <textarea
                      name="fact"
                      aria-label="事实原文"
                      readOnly={!editable}
                      maxLength={2000}
                      defaultValue={record.fact_text}
                    />
                  </label>
                  <label>
                    教师观察
                    <textarea
                      name="observation"
                      aria-label="教师观察"
                      readOnly={!editable}
                      maxLength={2000}
                      defaultValue={record.observation_text}
                    />
                  </label>
                  {editable && <Field label="更正理由" name="reason" maxLength={500} />}
                  <details>
                    <summary>原版本与留史</summary>
                    {activity?.records
                      .filter((item) => item.record_id === record.record_id)
                      .map((item) => (
                        <p key={item.version}>
                          v{item.version} ·{" "}
                          {item.fact_text || item.observation_text} ·{" "}
                          {displayTime(item.recorded_at)}
                        </p>
                      ))}
                  </details>
                </>
              )}
              {(form === "complete" || form === "cancel") && (
                <Field
                  label={
                    form === "complete" ? "完成结果 / 核对证据" : "取消原因"
                  }
                  name="evidence"
                  maxLength={500}
                />
              )}
              {!(["reauth", "reissue", "logout-all"] as Form[]).includes(form) && <p className="r1-muted">
                下一步只生成预览，不会立即写入正式业务事实。
              </p>}
              <button className="r1-primary" disabled={busy || (!editable && !(["class", "reauth", "reissue", "logout-all"] as Form[]).includes(form))}>
                {(["reauth", "reissue", "logout-all"] as Form[]).includes(form) ? "明确执行身份操作" : "生成预览"}
              </button>
            </form>
        </R1Dialog>
      )}
      {pending && (
        <R1Dialog titleId="r1-preview-title" busy={busy} onDismiss={() => void action(async () => {
          await request(`${workspace(session)}/commands/reject`, { proposal_id: pending.proposal.proposal_id }, session.csrf_token)
          setPending(null)
        })}>
            <h2 id="r1-preview-title">确认这次变更</h2>
            {error && <p className="r1-error" role="alert">{error}</p>}
            <p>
              {pending.proposal.risk === "W2"
                ? "需要你明确批准后才能提交。"
                : "请核对服务端预览，再明确提交。"}
              有效至 {displayTime(pending.proposal.expires_at)}
            </p>
            <dl>
              {Object.entries(pending.proposal.payload).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{value === null ? "无" : String(value)}</dd>
                </div>
              ))}
            </dl>
            <details>
              <summary>完整性摘要</summary>
              {pending.proposal.payload_hash}
            </details>
            <div className="r1-toolbar">
              <button
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    await request(
                      `${workspace(session)}/commands/reject`,
                      { proposal_id: pending.proposal.proposal_id },
                      session.csrf_token,
                    )
                    setPending(null)
                  })
                }
              >
                放弃变更
              </button>
              <button disabled={busy} onClick={() => void action(checkCommit)}>核对提交结果（不重复写入）</button>
              <button
                className="r1-primary"
                disabled={busy}
                onClick={() => void action(commit)}
              >
                {busy
                  ? "正在处理…"
                  : pending.proposal.risk === "W2"
                    ? "明确批准并提交"
                    : "确认提交"}
              </button>
            </div>
            <p className="r1-muted">网络失败可重试同一回执，不会重复创建。</p>
        </R1Dialog>
      )}
      {issuedCodes && <R1Dialog titleId="r1-kit-title"><h2 id="r1-kit-title">离线恢复码 · 仅显示一次</h2><p>旧恢复码和旧会话已撤销。请离线保存；不会写入本地缓存、模型或支持包。</p><pre>{issuedCodes.join("\n")}</pre><button className="r1-primary" onClick={() => setIssuedCodes(null)}>我已离线保存新的恢复码</button></R1Dialog>}
    </div>
  )
}

function Field({
  label,
  required = true,
  ...props
}: {
  label: string
  required?: boolean
  name: string
  type?: string
  maxLength?: number
  defaultValue?: string
  readOnly?: boolean
  step?: string
}) {
  return (
    <label>
      {label}
      <input {...props} required={required} />
    </label>
  )
}
function RecordCard({
  item,
  name,
  editable,
  canCreateTask,
  onCorrect,
  onTask,
}: {
  item: RecordItem
  name: string
  editable: boolean
  canCreateTask: boolean
  onCorrect: () => void
  onTask: () => void
}) {
  return (
    <article className="r1-card">
      <header>
        <strong>
          {name} · {kinds[item.kind] || item.kind}
        </strong>
        <small>v{item.version}</small>
      </header>
      <p>{item.fact_text}</p>
      {item.observation_text && <p>教师观察：{item.observation_text}</p>}
      <small className="r1-muted">
        发生 {displayTime(item.occurred_at)} · 记录{" "}
        {displayTime(item.recorded_at)} · 来源：教师确认 / 合成
      </small>
      {item.revision_reason && <p>更正理由：{item.revision_reason}</p>}
      <div className="r1-toolbar">
        <button disabled={!canCreateTask} onClick={onTask}>
          基于事实建立跟进
        </button>
        <button onClick={onCorrect}>
          {editable ? "查看版本 / 更正" : "查看历史版本"}
        </button>
      </div>
    </article>
  )
}

function Login({
  error,
  busy,
  onError,
  onSession,
  onProbeSession,
}: {
  error: string
  busy: boolean
  onError: (reason: unknown) => void
  onSession: (session: Session) => void
  onProbeSession: (session: Session) => void
}) {
  const [mode, setMode] = useState<"login" | "recover" | "reset">("login")
  const [pending, setPending] = useState(false)
  const [recoveryCsrf, setRecoveryCsrf] = useState("")
  const [codes, setCodes] = useState<string[] | null>(null)
  const [newSession, setNewSession] = useState<Session | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending || busy) return
    const data = new FormData(event.currentTarget)
    setPending(true)
    try {
      if (mode === "reset") {
        const session = await identityRequest("kit",
          "/api/identity/recovery/complete",
          { password: String(data.get("password")) },
          recoveryCsrf,
        )
        setCodes(session.recovery_codes || [])
        setNewSession(session)
      } else {
        const context = await identityRequest("challenge",
          "/api/identity/context",
        )
        if (mode === "recover") {
          const result = await identityRequest("challenge",
            "/api/identity/recovery/exchange",
            { code: String(data.get("code")) },
            context.csrf_token,
          )
          setRecoveryCsrf(result.csrf_token)
          setMode("reset")
        } else
          onSession(
            await identityRequest("session",
              "/api/identity/login",
              { password: String(data.get("password")) },
              context.csrf_token,
            ),
          )
      }
    } catch (reason) {
      if (reason instanceof IdentityOutcomeUnknown) { setMode("login"); setRecoveryCsrf("") }
      onError(reason)
    } finally {
      setPending(false)
    }
  }
  return (
    <main className="r1-auth">
      <section>
        <small>CLASSMATTER · 本地合成工作台</small>
        <h1>{mode === "login" ? "回到你的班级工作" : "恢复 owner 访问"}</h1>
        {error && (
          <p role="alert" className="r1-error">
            {error}
          </p>
        )}
        {codes ? (
          <>
            <p>请离线保存新的单次恢复码。旧密码、旧会话和旧恢复码均已失效。</p>
            <pre>{codes.join("\n")}</pre>
            <button
              onClick={() => {
                if (newSession) {
                  const { recovery_codes: _, ...clean } = newSession
                  onSession(clean)
                }
                setCodes(null)
                setNewSession(null)
              }}
            >
              我已离线保存，进入工作台
            </button>
          </>
        ) : (
          <form onSubmit={submit}>
            {mode === "recover" ? (
              <Field label="离线恢复码" name="code" maxLength={160} />
            ) : (
              <Field
                label={mode === "reset" ? "新密码（至少16字符）" : "Owner 密码"}
                name="password"
                type="password"
                maxLength={256}
              />
            )}
            <button className="r1-primary" disabled={pending || busy}>
              {pending
                ? "处理中…"
                : mode === "login"
                  ? "登录"
                  : mode === "recover"
                    ? "兑换恢复访问"
                    : "设置新密码"}
            </button>
          </form>
        )}
        <button
          disabled={pending}
          onClick={() => {
            setMode(mode === "login" ? "recover" : "login")
            setRecoveryCsrf("")
          }}
        >
          {mode === "login" ? "使用离线恢复码" : "返回登录"}
        </button>
        {mode === "login" && !codes && <button disabled={pending || busy} onClick={() => {
          setPending(true)
          void identityRequest("session", "/api/identity/session")
            .then(value => { onProbeSession(value) })
            .catch(reason => { onError(reason instanceof ApiError && reason.status === 401
              ? new Error("当前没有可用登录状态。只读核对没有重新执行身份操作，请用已知密码登录；重置后尝试刚设置的新密码。") : reason) })
            .finally(() => setPending(false))
        }}>核对当前登录状态（只读）</button>}
        <details>
          <summary>首次使用</summary>
          <p>
            先由本机 owner 在终端运行{" "}
            <code>uv run python local.py bootstrap</code>{" "}
            设置密码并保存恢复码。网页不能自行获得初始化权限。
          </p>
        </details>
        <p className="r1-muted">
          仅合成开发数据。服务失败不会回退为 mock 数据。
        </p>
      </section>
    </main>
  )
}
