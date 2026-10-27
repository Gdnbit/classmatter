import { useEffect, useState } from "react"
import type { Activity, Classroom, Student } from "./api"
import { workSummary } from "./work-summary"

export function WorkSummary({ classroom, activity, students, fresh, onDraftChange }: {
  classroom: Classroom; activity: Activity; students: Student[]; fresh: boolean; onDraftChange: (value: boolean) => void
}) {
  const [draft, setDraft] = useState<{ basis: string; text: string; original: string } | null>(null)
  const [notice, setNotice] = useState("")
  useEffect(() => { onDraftChange(!!draft); return () => onDraftChange(false) }, [!!draft, onDraftChange])
  useEffect(() => {
    if (!draft) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = "" }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [!!draft])
  let current: ReturnType<typeof workSummary> | null = null, failure = ""
  try { current = workSummary(classroom, activity, students) }
  catch (error) { failure = error instanceof Error ? error.message : "来源无法整理。" }
  const stale = !fresh || !current || draft?.basis !== current.basis
  return <section className="r1-card" aria-label="班级工作小结">
    <h2>班级工作小结</h2>
    <p>复用当前查询的记录与任务，无需重复录入。仅在本页临时编辑；离开、刷新、退出即丢失，请先手动复制到受信文档。不保存到聊天、数据库或浏览器缓存。</p>
    <button disabled={!fresh || !current || !!draft} onClick={() => {
      if (current) { setDraft({ basis: current.basis, text: current.text, original: current.text }); setNotice("") }
    }}>整理班级工作小结</button>
    {failure && <p role="alert">{failure}</p>}
    {draft && <>
      <p role="status">{stale ? "来源已变化或尚未重新核对；不能标作当前小结复制。保留编辑供人工核对，可丢弃后重新整理。" : "来源版本与当前查询一致；编辑文字仍需本人核对。"}</p>
      <label style={{ display: "grid", gap: 8 }}>可编辑小结（未保存）<textarea
        style={{ width: "100%", boxSizing: "border-box", minHeight: 320, font: "inherit", lineHeight: 1.6 }} rows={16} maxLength={100000} value={draft.text}
        onChange={event => { setDraft({ ...draft, text: event.target.value }); setNotice("") }} /></label>
      <details><summary>生成时的只读来源摘录（不是当前事实保证）</summary><pre style={{ whiteSpace: "pre-wrap" }}>{draft.original}</pre></details>
      <button disabled={stale || !draft.text.trim()} onClick={async () => {
        // No external destination, native file path or generic download privilege.
        try { await navigator.clipboard.writeText(draft.text); setNotice("已按本人操作复制；未保存或发送。") }
        catch { setNotice("系统未允许剪贴板写入；可在文本框全选后手动复制。") }
      }}>复制已核对草稿</button>
      <button onClick={() => { setDraft(null); setNotice("已丢弃本页草稿，未更改任何业务数据。") }}>丢弃小结草稿</button>
    </>}
    {notice && <p role="status">{notice}</p>}
  </section>
}
