import { useEffect, useLayoutEffect, useRef, useState } from "react"
import type { Activity, Classroom, Student } from "./api"
import { workSummary } from "./work-summary"

export function WorkSummary({ classroom, activity, students, fresh, onDraftChange, onDocumentDraft }: {
  classroom: Classroom; activity: Activity; students: Student[]; fresh: boolean; onDraftChange: (value: boolean) => void
  onDocumentDraft?: (text: string) => boolean
}) {
  const [draft, setDraft] = useState<{ basis: string; text: string; original: string } | null>(null)
  const [notice, setNotice] = useState("")
  const copyGeneration = useRef(0)
  useEffect(() => () => { copyGeneration.current++ }, [])
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
  useLayoutEffect(() => { copyGeneration.current++ }, [draft?.text, draft?.basis, current?.basis, fresh])
  return <section className="r1-card" aria-label="班级工作小结">
    <h2>班级工作小结</h2>
    <p>根据已有记录和任务整理小结。{onDocumentDraft
      ? "请转入文档后保存，离开前保留草稿。"
      : "草稿尚未保存，离开前请复制。"}</p>
    <button disabled={!fresh || !current || !!draft} onClick={() => {
      if (current) { setDraft({ basis: current.basis, text: current.text, original: current.text }); setNotice("") }
    }}>整理班级工作小结</button>
    {failure && <p role="alert">{failure}</p>}
    {draft && <>
      <p role="status">{stale ? "记录已更新，请重新整理后再复制。" : "请核对内容后使用。"}</p>
      <label style={{ display: "grid", gap: 8 }}>可编辑小结（未保存）<textarea aria-label="可编辑小结（未保存）"
        style={{ width: "100%", boxSizing: "border-box", minHeight: 320, font: "inherit", lineHeight: 1.6 }} rows={16} maxLength={100000} value={draft.text}
        onChange={event => { setDraft({ ...draft, text: event.target.value }); setNotice("") }} /></label>
      <details><summary>查看整理依据</summary><pre style={{ whiteSpace: "pre-wrap" }}>{draft.original}</pre></details>
      <button disabled={stale || !draft.text.trim()} onClick={async () => {
        // No external destination, native file path or generic download privilege.
        const generation = ++copyGeneration.current
        try { await navigator.clipboard.writeText(draft.text); if (generation === copyGeneration.current) setNotice("已复制") }
        catch { if (generation === copyGeneration.current) setNotice("复制失败，请选择文字复制。") }
      }}>复制已核对草稿</button>
      {onDocumentDraft && <button disabled={stale || !draft.text.trim()} onClick={() => {
        if (onDocumentDraft(draft.text)) { setDraft(null); onDraftChange(false) }
        else setNotice("暂时无法打开文档，请先复制草稿。")
      }}>转入文档草稿</button>}
      <button onClick={() => { setDraft(null); setNotice("已丢弃草稿。") }}>丢弃小结草稿</button>
    </>}
    {notice && <p role="status">{notice}</p>}
  </section>
}
