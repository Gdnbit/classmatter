import type { Attribution } from "./durable-conversation"

export function AttributionLabel({ value }: { value?: Attribution }) {
  if (!value) return null
  return <details className="r1-muted r1-attribution"><summary>
    {value.content_authority === "assistant-unverified" ? "AI 草稿 · 待核对" : value.origin === "source-import" ? "导入内容" : "创建记录"}
  </summary><p>{value.content_authority === "assistant-unverified" ? "AI 生成，请核对后使用。" : "已保存的工作内容。"}</p>
  </details>
}
