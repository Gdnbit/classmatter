// Cookie credentials stay HttpOnly. No business data/token localStorage cache.
export type Session = {
  schema_version: "class-os.identity.v1"
  csrf_token: string
  subject: {
    owner_id: string
    workspace_id: string
  }
  recovery_codes?: string[]
}
export type Classroom = {
  class_id: string
  term_id: string
  name: string
  term_name: string
  version: number
  status?: "active" | "archived"
}
export type TermMetadata = {
  schema_version: "class-os.term-metadata.v1"
  class_id: string
  term_id: string
  name: string
  start_date: string
  end_date: string
  version: number
}
export type Student = {
  student_id: string
  name: string
  version: number
  status: "active" | "inactive"
}
export type RecordItem = {
  record_id: string
  student_id: string
  version: number
  kind: string
  occurred_at: string
  recorded_at: string
  fact_text: string
  observation_text: string
  source: string
  related_record_id: string | null
  revision_kind: string
  revision_reason: string
}
export type TaskItem = {
  task_id: string
  title: string
  student_id: string | null
  source_record_id: string | null
  due_at: string | null
  status: "not-started" | "in-progress" | "waiting" | "done" | "cancelled"
  evidence: string
  version: number
  overdue: boolean
}
export type Activity = {
  as_of: string
  records: RecordItem[]
  tasks: TaskItem[]
}
export type Identifier = {
  identifier_id: string
  student_id: string
  authority: string
  identifier_type: string
  value: string
  valid_from: string
  valid_to: string | null
}
export type Duplicate = {
  left_student_id: string
  right_student_id: string
  reason: string
}
export type Command = {
  command: string
  class_id?: string
  term_id?: string
  [field: string]: string | number | boolean | null | undefined
}
export type Proposal = {
  schema_version: "class-os.roster.v1"
  proposal_id: string
  payload_hash: string
  risk: "W1" | "W2"
  expires_at: string
  payload: Command
}

export type QuerySource = {
  entity: "query_receipt"
  id: string
  version: 1
  projection_hash: string
  as_of: string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public requestId: string,
  ) {
    super(
      status === 401
        ? "登录已失效，请重新登录；未提交的草稿不会写入。"
        : status === 409
          ? "数据版本或操作状态已变化，请刷新后重新预览。"
          : status === 403
            ? "请求未通过本机来源/确认校验。"
            : status === 503
              ? "服务暂时不可用。若正在保存，请先核对原请求结果，不要重复新建。"
              : status >= 500 && status < 600
                ? "请求未完成。若正在保存，请先核对原请求结果，不要重复新建。"
                : "请求未完成，请检查服务后重试。",
    )
  }
}

export async function request<T>(
  path: string,
  body?: unknown,
  csrf?: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    signal,
    headers:
      body === undefined
        ? (csrf ? { "x-class-os-csrf": csrf } : {})
        : { "content-type": "application/json", "x-class-os-csrf": csrf || "" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok)
    throw new ApiError(
      response.status,
      response.headers.get("x-request-id") || "",
    )
  const result: unknown = await response.json()
  if (
    !result ||
    typeof result !== "object" ||
    !("schema_version" in result) ||
    typeof result.schema_version !== "string" ||
    !result.schema_version.startsWith("class-os.")
  ) {
    throw new Error("服务响应契约不匹配，未使用演示数据回退。")
  }
  return result as T
}

export type AuditPage = {
  schema_version: "class-os.business-audit.v1"
  as_of: string
  truncated: boolean
  partial_history: true
  entries: {
    event_id: string
    action: string
    outcome: "allowed" | "denied"
    occurred_at: string
    proposal_id: string | null
    payload_hash: string | null
    receipt_id: string | null
    resource_id: string | null
    resource_version: number | null
  }[]
}

export type CommandReceipt = { receipt_id: string; resource_id: string; version: number }
export type CommandState = {
  schema_version: "class-os.command-status.v1"
  proposal_id: string
  payload_hash: string
  status: "committed" | "not_committed" | "unavailable"
  receipt: CommandReceipt | null
}

export function workspace(session: Session) {
  return `/api/workspaces/${session.subject.workspace_id}`
}
export function scope(session: Session, classroom: Classroom) {
  return `${workspace(session)}/classes/${classroom.class_id}/terms/${classroom.term_id}`
}
