// Presentation only. Original command payloads remain untouched for validation and commit.
const actions: Record<string, string> = {
  "class.create": "建立班级与学期", "class.update": "修改班级名称", "class.archive": "归档班级", "term.update": "更正学期信息",
  "student.create": "添加学生", "student.update_name": "更正学生姓名", "student.deactivate": "停用学生", "student.update_identifier": "更正学生信息",
  "identifier.add": "添加学生信息", "identifier.correct": "更正学生信息", "student.add_identifier": "添加学生信息",
  "record.create": "添加记录", "record.correct": "更正记录", "record.supersede": "更正记录", "task.create": "建立跟进", "task.update": "修改跟进", "task.complete": "完成跟进", "task.cancel": "取消跟进",
  "document.read": "查看文档", "document.create": "创建文档", "document.revise": "修改文档", "document.archive": "归档文档", "document.restore": "恢复文档",
  "model_configuration.save": "保存模型配置", "model_configuration.clear": "移除模型配置", "exit_export.create": "导出数据",
  "command.preview": "预览变更", "command.approve": "确认变更", "command.commit": "保存变更", "command.reject": "放弃变更",
}
const fields: Record<string, string> = { command: "操作", name: "名称", term_name: "学期", start_date: "开始日期", end_date: "结束日期", title: "标题", status: "状态", kind: "记录类型", fact_text: "事实记录", observation_text: "教师观察", occurred_at: "发生时间", recorded_at: "记录时间", due_at: "截止时间", evidence: "结果说明", reason: "原因", revision_reason: "更正原因", source: "来源", authority: "信息来源", identifier_type: "信息类型", value: "内容", valid_from: "开始生效", valid_to: "结束生效", body: "正文", format: "正文格式", protocol: "服务接口", model: "模型", base_url: "服务地址" }
const values: Record<string, string> = { "not-started": "未开始", "in-progress": "进行中", waiting: "等待别人", done: "已完成", cancelled: "已取消", active: "在班", inactive: "已停用", "plain-text": "纯文本", markdown: "Markdown", "trusted-ui-synthetic": "教师录入", "trusted-ui": "教师录入", attendance: "考勤", discipline: "纪律", homework: "作业", learning: "学习", other: "其他" }
const targets: Record<string, string> = { class_id: "班级", term_id: "学期", student_id: "学生", record_id: "记录", task_id: "跟进", source_record_id: "来源记录", related_record_id: "关联记录", identifier_id: "学生信息" }
Object.assign(fields, { previous_name: "原名称", previous_start_date: "原开始日期", previous_end_date: "原结束日期" })
Object.assign(values, { ordinary_fact: "事实记录", teacher_observation: "教师观察", attendance_late_fact: "迟到", attendance_absent_fact: "缺勤", leave_requested_fact: "请假申请", leave_approved_fact: "请假批准", leave_returned_fact: "销假", homework_missing_fact: "作业未交", homework_submitted_fact: "作业补交", discipline_fact: "纪律记录", conversation_fact: "谈话记录" })
export function actionName(action: string) { return actions[action] || "操作记录" }
export function userMessage(message: string) {
  if (/Failed to fetch|NetworkError|network request/i.test(message)) return "连接中断，请稍后重试。"
  if (/契约|绑定校验|回执|快照|幂等|原请求|原键|UUID|schema|\bQG\b|\bBCG\b|\bToken\b/i.test(message)) return "暂时无法确认结果，请保留当前内容并核对操作结果。"
  return message
}
export function previewFields(payload: Record<string, unknown>, names: Record<string, string> = {}) {
  return Object.entries(payload).flatMap(([key, value]) => {
    if (key === "due_at" && payload.change_due_date === false) return []
    if (targets[key]) return typeof value === "string" && names[value] ? [[targets[key], names[value]]] : []
    if (!fields[key] || value === undefined) return []
    const text = key === "command" ? actionName(String(value)) : value === null || value === "" ? key === "due_at" ? "不设置截止时间" : "未填写" : typeof value === "boolean" ? value ? "是" : "否" : values[String(value)] || String(value)
    return [[fields[key], text]]
  })
}
