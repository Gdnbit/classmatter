import { createParser } from "eventsource-parser"

export type RuntimeEvent = {
  cursor: number
  run_id: string
  type: string
  payload: Record<string, unknown>
}
const types = new Set(["run.started", "tool.started", "tool.completed", "draft.available", "message.delta", "run.completed", "run.failed"])
const terminals = new Set(["run.completed", "run.failed"])

// Mature library owns SSE framing. This layer validates the project envelope;
// truncated/reordered streams never become successful or automatically replay.
export async function consumeEvents(response: Response, onEvent: (event: RuntimeEvent) => void) {
  if (!response.ok || !response.headers.get("content-type")?.startsWith("text/event-stream") || !response.body) throw new Error("Agent 流未建立，未进行任何业务提交。")
  const reader = response.body.getReader()
  const decoder = new TextDecoder("utf-8", { fatal: true })
  let count = 0, bytes = 0, run = "", terminal = false
  const parser = createParser({ maxBufferSize: 65536,
    onError(error) { throw error }, onRetry() { throw new Error("不允许自动重放 Agent 操作") },
    onEvent(frame) {
      const item = JSON.parse(frame.data) as RuntimeEvent
      if (terminal || count >= 64 || !item || Object.keys(item).sort().join(",") !== "cursor,payload,run_id,type"
        || item.cursor !== count + 1 || typeof item.run_id !== "string" || !item.run_id || (run && item.run_id !== run)
        || !types.has(item.type) || !item.payload || typeof item.payload !== "object" || Array.isArray(item.payload)
        || frame.id !== String(item.cursor) || frame.event !== item.type || (!count && item.type !== "run.started")
        || new TextEncoder().encode(frame.data).length > 32768) throw new Error("Agent 事件校验失败，未采纳结果。")
      count++; run = item.run_id; terminal = terminals.has(item.type); onEvent(item)
    } })
  try {
    while (true) {
      const item = await reader.read()
      if (item.done) break
      bytes += item.value.byteLength
      if (bytes > 150000) throw new Error("Agent 输出超出上限")
      parser.feed(decoder.decode(item.value, { stream: true }))
    }
    parser.feed(decoder.decode()); parser.reset({ consume: true })
    if (!terminal) throw new Error("连接中断，没有完成结果；可手动重新查询。")
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}
