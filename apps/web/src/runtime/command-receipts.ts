import { receipt as receiptSchema, state as stateSchema } from "./command-receipts-validators.cjs"
import type { Command, CommandReceipt, CommandState, Proposal } from "./api"

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const unknown = () => new Error("提交结果未通过绑定校验，尚未确认保存。请按原请求核对提交结果，不要重复新建。")

function target(command: Command): { id: string; version: number } {
  let field: string
  let changed = false
  let zeroBased = false
  switch (command.command) {
    case "class.create": field = "class_id"; break
    case "student.create": field = "student_id"; break
    case "record.create": field = "record_id"; break
    case "task.create": field = "task_id"; break
    case "exit_export.create": field = "export_id"; break
    case "class.update": case "class.archive": field = "class_id"; changed = true; break
    case "term.update": field = "term_id"; changed = true; break
    case "student.update_name": case "student.update_identifier": case "student.deactivate":
      field = "student_id"; changed = true; break
    case "record.correct": case "record.supersede": field = "record_id"; changed = true; break
    case "task.update": case "task.complete": case "task.cancel": field = "task_id"; changed = true; break
    case "model_configuration.save": case "model_configuration.clear":
      field = "candidate_id"; changed = true; zeroBased = true; break
    default: throw unknown()
  }
  const id = command[field]
  if (typeof id !== "string" || !uuid.test(id)) throw unknown()
  let version = 1
  if (changed) {
    const before = command.expected_version
    if (typeof before !== "number" || !Number.isSafeInteger(before) || before < (zeroBased ? 0 : 1) || before >= 2147483647) throw unknown()
    version = before + 1
  }
  return { id, version }
}

function bindReceipt(data: CommandReceipt, command: Command): CommandReceipt {
  const expected = target(command)
  if (data.resource_id !== expected.id || !Number.isSafeInteger(data.version)
    || data.version < 1 || data.version > 2147483647 || data.version !== expected.version) throw unknown()
  return Object.freeze({ receipt_id: data.receipt_id, resource_id: data.resource_id, version: data.version })
}

export function decodeCommandReceipt(data: unknown, command: Command): CommandReceipt {
  const valid = receiptSchema(data); receiptSchema.errors = null
  if (!valid || !data || typeof data !== "object" || !Object.prototype.hasOwnProperty.call(data, "schema_version") || !("schema_version" in data)
    || data.schema_version !== "class-os.roster.v1") throw unknown()
  return bindReceipt(data as unknown as CommandReceipt, command)
}

export function decodeCommandState(data: unknown, proposal: Proposal): CommandState {
  const valid = stateSchema(data); stateSchema.errors = null
  if (!valid || !data || typeof data !== "object" || !Object.prototype.hasOwnProperty.call(data, "schema_version") || !("schema_version" in data)
    || data.schema_version !== "class-os.command-status.v1") throw unknown()
  const value = data as CommandState
  if (value.proposal_id !== proposal.proposal_id || value.payload_hash !== proposal.payload_hash
    || (value.status === "committed") !== (value.receipt !== null)) throw unknown()
  const receipt = value.receipt === null ? null : bindReceipt(value.receipt, proposal.payload)
  return Object.freeze({ schema_version: value.schema_version, proposal_id: value.proposal_id,
    payload_hash: value.payload_hash, status: value.status, receipt })
}

export function decodeApproval(data: unknown): string {
  if (!data || typeof data !== "object" || Array.isArray(data)
    || Object.keys(data).sort().join(",") !== "approval,schema_version"
    || !("schema_version" in data) || data.schema_version !== "class-os.roster.v1"
    || !("approval" in data) || typeof data.approval !== "string"
    || data.approval.length < 32 || data.approval.length > 128) {
    throw new Error("批准结果未通过校验，未继续提交。请核对当前预览，不要重复新建。")
  }
  return data.approval
}
