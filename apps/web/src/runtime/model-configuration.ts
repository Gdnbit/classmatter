import { validate, status, staged } from "./model-configuration-validator.cjs"
import { request, workspace, type Session, type Command } from "./api"

export type ModelConfiguration = { protocol: "chat-completions" | "responses"; model: string; base_url: string }
export type ConfigurationResult = {
  schema_version: "class-os.model-configuration.v1"
  status: "syntax-valid-not-enabled"
  configuration: ModelConfiguration
  persisted: false
  enabled: false
  network_tested: false
}

export function decodeConfiguration(data: unknown, submitted: ModelConfiguration): ConfigurationResult {
  const valid = validate(data)
  validate.errors = null
  if (!valid) throw new Error("配置校验响应不匹配，未采纳；模型仍未启用。")
  const result = data as ConfigurationResult
  if (result.configuration.protocol !== submitted.protocol || result.configuration.model !== submitted.model
      || result.configuration.base_url !== submitted.base_url) {
    throw new Error("配置校验响应与本次输入不匹配，未采纳；模型仍未启用。")
  }
  return result
}

export async function validateConfiguration(session: Session, candidate: ModelConfiguration, signal?: AbortSignal): Promise<ConfigurationResult> {
  return decodeConfiguration(await request<unknown>(`${workspace(session)}/agent/configuration/validate`, candidate, session.csrf_token, signal), candidate)
}

export type ModelStatus = {
  schema_version: "class-os.model-status.v1"
  storage_available: boolean
  version: number
  candidate_id: string | null
  configuration: ModelConfiguration | null
  key_configured: boolean
  network_permitted: boolean
  test_passed: boolean
  mode: "offline" | "configured-api" | "stale"
}
export function decodeModelStatus(data: unknown): ModelStatus {
  const valid = status(data); status.errors = null
  if (!valid) throw new Error("模型状态响应不匹配，未采纳。")
  const value = data as ModelStatus
  if ((value.key_configured !== (value.configuration !== null))
      || (value.version === 0) !== (value.candidate_id === null)
      || (value.mode === "configured-api" && (!value.key_configured || !value.network_permitted))) {
    throw new Error("模型状态不一致，未采纳。")
  }
  return value
}
export async function getModelStatus(session: Session, signal?: AbortSignal): Promise<ModelStatus> {
  return decodeModelStatus(await request(`${workspace(session)}/agent/configuration/status`, undefined, undefined, signal))
}
export async function stageModel(session: Session, candidate: ModelConfiguration, api_key: string, version: number, signal?: AbortSignal): Promise<Command> {
  const data = await request<unknown>(`${workspace(session)}/agent/configuration/stage`, { ...candidate, api_key, expected_version: version }, session.csrf_token, signal)
  const valid = staged(data); staged.errors = null
  if (!valid) throw new Error("密钥候选响应不匹配，尚未保存；请重新核对。")
  const result = data as { command: Command }
  if (result.command.command !== "model_configuration.save" || result.command.expected_version !== version
      || result.command.protocol !== candidate.protocol || result.command.model !== candidate.model || result.command.base_url !== candidate.base_url) {
    throw new Error("配置候选与本次输入不一致，未进入预览。")
  }
  return result.command
}
export async function modelControl(session: Session, operation: "test" | "enable" | "disable", state: ModelStatus, signal?: AbortSignal): Promise<ModelStatus> {
  if (!["test", "enable", "disable"].includes(operation)) throw new Error("未知模型控制操作，未发送。")
  const body = operation === "disable" ? {} : { candidate_id: state.candidate_id, version: state.version, confirm_network: true,
    ...(operation === "test" ? { request_id: crypto.randomUUID() } : {}) }
  return decodeModelStatus(await request(`${workspace(session)}/agent/configuration/${operation}`, body, session.csrf_token, signal))
}
