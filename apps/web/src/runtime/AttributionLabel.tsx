import type { Attribution } from "./durable-conversation"

export function AttributionLabel({ value }: { value?: Attribution }) {
  if (!value) return null
  return <details className="r1-muted r1-attribution"><summary>
    {value.content_authority === "assistant-unverified" ? "AI 历史内容 · 未核验" : value.origin === "source-import" ? "来源作者 · 已导入" : "来源作者 · 本机拥有者"}
  </summary><p>创建者：{value.created_by || "AI 生成，不是人物事实"}</p>
    {value.last_modified_by && <p>最近修改者：{value.last_modified_by}</p>}
    {value.source_owner_id && <p>原拥有者：{value.source_owner_id} · 来源版本 {value.source_version}</p>}
    {value.source_workspace_id && <p>原工作区：{value.source_workspace_id}</p>}
  </details>
}
