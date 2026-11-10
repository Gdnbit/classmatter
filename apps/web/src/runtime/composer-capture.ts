import { ApiError, workspace, type Session } from './api'
import type { ModelStatus } from './model-configuration'
import validators from './workspace-chat-validators.cjs'

export type Reasoning = 'default' | 'low' | 'medium' | 'high'
export const reasoningLabels: Record<Reasoning, string> = { default: '默认', low: '轻度', medium: '适中', high: '深入' }
export function supportsReasoning(status: ModelStatus | null) {
  const config = status?.configuration
  return !!config && (/^(gpt-5|o[1-9])/.test(config.model)
    || config.base_url.replace(/\/$/, '') === 'https://generativelanguage.googleapis.com/v1beta/openai' && config.model.startsWith('gemini-3'))
}
const messages: Record<string, string> = {
  unsupported_file: '请选择文字、Office 文档、PDF、图片或音频文件。', invalid_file: '文件无法读取，请检查后重试。',
  file_too_large: '文件较大，请选择不超过 2 MB 的文件。', no_readable_text: '没有识别到可用文字。',
  capture_too_long: '内容超过本条消息的长度，请分段添加。', invalid_encoding: '文字编码无法识别，请另存为 UTF-8 后重试。',
  model_required: '请先连接支持图片和语音的模型。', capture_busy: '正在处理其他请求，请稍后重试。', capture_failed: '识别未完成，请重试。',
}
export async function importCapture(session: Session, file: File, capacity: number, signal: AbortSignal) {
  if (!file.size || file.size > 2 * 1024 * 1024) throw new Error(messages.file_too_large)
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    const abort = () => { clean(); reader.abort(); reject(new DOMException('Aborted', 'AbortError')) }
    signal.addEventListener('abort', abort, { once: true })
    const clean = () => signal.removeEventListener('abort', abort)
    reader.onerror = () => { clean(); reject(new Error(messages.invalid_file)) }
    reader.onabort = clean
    reader.onload = () => { clean(); resolve(String(reader.result).split(',')[1] || '') }
    if (signal.aborted) abort(); else reader.readAsDataURL(file)
  })
  signal.throwIfAborted()
  let response: Response
  try {
    response = await fetch(`${workspace(session)}/composer/capture`, { method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal,
      headers: { 'content-type': 'application/json', 'x-class-os-csrf': session.csrf_token }, body: JSON.stringify({ name: file.name, data, capacity }) })
  } catch (error) { signal.throwIfAborted(); throw new Error('读取未完成，请检查连接后重试。') }
  if (response.status === 401 || response.status === 403) throw new ApiError(response.status, response.headers.get('x-request-id') || '')
  let value
  try { value = await response.json() } catch { signal.throwIfAborted(); throw new Error(messages.capture_failed) }
  signal.throwIfAborted()
  if (!response.ok) throw new Error(messages[value.error] || messages.capture_failed)
  if (!validators.captureoutput(value) || [...value.text].length > capacity) throw new Error(messages.capture_failed)
  return value.text as string
}
