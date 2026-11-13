import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ApiError } from './api'
import { documentClient, type DocumentView, type OfficeFormat } from './documents'

export function DocumentExportActions({ value, api, enabled, unsaved, onError }: {
  value: Pick<DocumentView, 'document_id' | 'version' | 'title'>; api: ReturnType<typeof documentClient>; enabled: boolean; unsaved: boolean; onError: (error: unknown) => void
}) {
  const [active, setActive] = useState<OfficeFormat | null>(null), [error, setError] = useState('')
  const operation = useRef<AbortController | null>(null)
  useLayoutEffect(() => () => { operation.current?.abort(); operation.current = null }, [value.document_id, value.version])
  useEffect(() => { if (!enabled) operation.current?.abort() }, [enabled])
  async function download(format: OfficeFormat) {
    if (!enabled || operation.current) return
    const controller = new AbortController()
    operation.current = controller; setActive(format); setError('')
    let objectUrl: string | null = null
    try {
      const file = await api.exportFile(value.document_id, value.version, format, controller.signal)
      controller.signal.throwIfAborted()
      const link = document.createElement('a')
      // Native hosts retain their exact same-origin route/MIME/size download
      // policy and Save dialog. They never accept arbitrary blob/file paths.
      objectUrl = window.classMatterDesktop ? null : URL.createObjectURL(file.blob)
      link.href = objectUrl || file.path
      link.download = (value.title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[ .]+$/, '') || 'ClassMatter') + '.' + format
      document.body.append(link); link.click(); link.remove()
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof ApiError && reason.status === 409 ? '文档已更新，请重新打开后导出。'
          : reason instanceof ApiError && reason.status === 413 ? '内容较长，请分成几份导出。' : '暂时无法导出，请重试。')
        if (reason instanceof ApiError && reason.status === 401) onError(reason)
      }
    } finally {
      if (objectUrl) setTimeout(() => URL.revokeObjectURL(objectUrl!), 1000)
      if (operation.current === controller) { operation.current = null; setActive(null) }
    }
  }
  return <span className="document-exports">
    {(['docx', 'pptx'] as const).map(format => <button key={format} type="button" disabled={!enabled || active !== null}
      aria-label={format === 'docx' ? '导出 Word' : '导出 PPT'} title={unsaved ? '请先保存修改' : undefined}
      onClick={() => void download(format)}>{active === format ? '导出中…' : format === 'docx' ? 'Word' : 'PPT'}</button>)}
    {error && <span role="alert">{error}</span>}
  </span>
}
