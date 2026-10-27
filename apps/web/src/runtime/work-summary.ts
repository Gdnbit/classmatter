import type { Activity, Classroom, RecordItem, Student } from "./api.ts"
import type { Attribution } from "./durable-conversation.ts"

const author = (value?: Attribution) => value
  ? `来源作者：${value.created_by || "未标注"} · 最近修改者：${value.last_modified_by || "未标注"} · ${value.origin} · 内容权威：${value.content_authority} · 原工作区：${value.source_workspace_id || "本机"} · 原拥有者：${value.source_owner_id || "本机"} · 原版本：${value.source_version ?? "无"}`
  : "来源作者：当前查询未提供作者元数据，不推断"

// Presentation of an already authorized QG snapshot, never a business writer.
export function workSummary(classroom: Classroom, activity: Activity, students: readonly Student[]) {
  const latest = new Map<string, RecordItem>()
  for (const record of activity.records) {
    if (!latest.has(record.record_id) || latest.get(record.record_id)!.version < record.version)
      latest.set(record.record_id, record)
  }
  const records = [...latest.values()].sort((a, b) => a.record_id.localeCompare(b.record_id))
  const tasks = [...activity.tasks].sort((a, b) => a.task_id.localeCompare(b.task_id))
  if (records.length + tasks.length > 100) throw new Error("来源超过100项；本切片不截断生成，请在原页面核对。")
  const names = new Map(students.map(student => [student.student_id, student.name]))
  const who = (id: string | null) => id ? `${names.get(id) || "未在当前名册"}（${id}）` : "全班任务"
  // Include the complete set and content, not just references selected earlier.
  // as_of/overdue are time-derived and do not identify a stored source version.
  const basis = JSON.stringify({ classroom, records, tasks: tasks.map(({ overdue: _, ...task }) => task),
    students: [...students].sort((a, b) => a.student_id.localeCompare(b.student_id)) })
  const lines = [`班级工作小结（待核对草稿）`, `${classroom.name} · ${classroom.term_name}`,
    `查询时点：${activity.as_of}`, `范围：当前授权班级/学期全部最新记录 ${records.length} 项、任务 ${tasks.length} 项；不是指定周/月报告。`,
    "本稿为规则整理，未调用模型；编辑内容不自动成为事实，不判定责任，不自动发送。", "", "记录来源（事实与教师观察分别标示）"]
  for (const record of records) lines.push(
    `[record:${record.record_id}@${record.version}] ${who(record.student_id)} · ${record.kind} · ${record.occurred_at}`,
    `事实字段：${record.fact_text || "（无）"}`, `教师观察字段（不等于事实）：${record.observation_text || "（无）"}`,
    `原始来源字段：${record.source}`, author(record.attribution), `修订：${record.revision_kind} · ${record.revision_reason || "（无）"}`, "")
  lines.push("任务来源（已登记状态，不代表责任转移）")
  for (const task of tasks) lines.push(`[task:${task.task_id}@${task.version}] ${task.title}`,
    `对象：${who(task.student_id)} · 状态：${task.status} · 截止：${task.due_at || "未设"}`,
    `关联记录：${task.source_record_id || "无"} · 已登记依据：${task.evidence || "无"}`, author(task.attribution), "")
  if (!records.length && !tasks.length) lines.push("当前无记录或任务；不能据此推断未发生事项或工作已完成。")
  const text = lines.join("\n")
  if (text.length > 64000) throw new Error("来源正文超过64000字符；未生成截断小结。")
  return { basis, text, recordCount: records.length, taskCount: tasks.length }
}
