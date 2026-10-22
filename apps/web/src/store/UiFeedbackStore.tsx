import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import { CheckCircle2, ChevronRight, Info, ShieldCheck, X } from "lucide-react"

export type DetailSection = {
  label: string
  value: string
}

export type DetailAction = {
  label: string
  tone?: "primary" | "default" | "danger"
  onSelect?: () => void
}

export type DetailPayload = {
  eyebrow?: string
  title: string
  description?: string
  status?: string
  sections?: DetailSection[]
  timeline?: string[]
  actions?: DetailAction[]
}

type ConfirmPayload = {
  title: string
  description: string
  confirmLabel?: string
  onConfirm: () => void
}

type UiFeedbackValue = {
  notify: (message: string) => void
  openDetail: (detail: DetailPayload) => void
  closeDetail: () => void
  requestConfirm: (payload: ConfirmPayload) => void
}

const UiFeedbackContext = createContext<UiFeedbackValue | null>(null)

export function UiFeedbackStore({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<string | null>(null)
  const [detail, setDetail] = useState<DetailPayload | null>(null)
  const [confirm, setConfirm] = useState<ConfirmPayload | null>(null)

  const notify = (message: string) => setToast(message)
  const closeDetail = () => setDetail(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2600)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if (!detail && !confirm) return
    const panel = document.querySelector<HTMLElement>(confirm ? ".confirm-dialog" : ".detail-sheet")
    if (!panel) return
    const previous = document.activeElement as HTMLElement | null
    const container = panel.closest(".overlay-backdrop")!
    const backgrounds = Array.from(container.parentElement?.children || []).filter(el => el !== container && el instanceof HTMLElement) as HTMLElement[]
    const oldInert = backgrounds.map(el => el.inert)
    backgrounds.forEach(el => { el.inert = true })
    panel.tabIndex = -1
    const buttons = () => Array.from(panel.querySelectorAll<HTMLElement>('button:not(:disabled), input, textarea, select, a[href], [tabindex="0"]')).filter(el => el.getClientRects().length)
    ;(buttons()[0] || panel).focus()
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation()
        if (confirm) setConfirm(null)
        else setDetail(null)
      }
      if (event.key === "Tab") {
        const items = buttons()
        const index = items.indexOf(document.activeElement as HTMLElement)
        if (!items.length) { event.preventDefault(); panel.focus(); return }
        if (event.shiftKey && index <= 0) { event.preventDefault(); items.at(-1)!.focus() }
        else if (!event.shiftKey && (index < 0 || index === items.length - 1)) { event.preventDefault(); items[0].focus() }
      }
    }
    document.addEventListener("keydown", handleKey, true)
    return () => {
      document.removeEventListener("keydown", handleKey, true)
      backgrounds.forEach((el, i) => { el.inert = oldInert[i] })
      if (previous?.isConnected) previous.focus()
    }
  }, [!!confirm, !!detail])

  return (
    <UiFeedbackContext.Provider
      value={{
        notify,
        openDetail: setDetail,
        closeDetail,
        requestConfirm: setConfirm,
      }}
    >
      {children}
      {detail && (
        <div
          className="overlay-backdrop"
          role="presentation"
          onMouseDown={closeDetail}
        >
          <section
            className="detail-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="detail-sheet-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="detail-sheet-head">
              <div>
                <p className="eyebrow">{detail.eyebrow || "详细信息"}</p>
                <h2 id="detail-sheet-title">{detail.title}</h2>
                {detail.description && <p>{detail.description}</p>}
              </div>
              <button
                className="icon-control"
                onClick={closeDetail}
                aria-label="关闭详情"
              >
                <X size={18} />
              </button>
            </header>
            {detail.status && (
              <div className="detail-status">
                <ShieldCheck size={16} />
                <span>{detail.status}</span>
              </div>
            )}
            {detail.sections && (
              <dl className="detail-facts">
                {detail.sections.map((section) => (
                  <div key={section.label}>
                    <dt>{section.label}</dt>
                    <dd>{section.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {detail.timeline && (
              <div className="detail-timeline">
                <h3>处理记录</h3>
                {detail.timeline.map((item, index) => (
                  <div key={item}>
                    <span>{index + 1}</span>
                    <p>{item}</p>
                  </div>
                ))}
              </div>
            )}
            <footer className="detail-sheet-actions">
              {(detail.actions || []).map((action) => (
                <button
                  key={action.label}
                  className={
                    action.tone === "primary"
                      ? "primary"
                      : action.tone === "danger"
                        ? "danger"
                        : ""
                  }
                  onClick={() => {
                    const dismissOnly = ["关闭", "知道了", "返回表格"].includes(action.label)
                    if (action.onSelect) action.onSelect()
                    else if (!dismissOnly) notify(`${action.label}尚未接入；本次没有生成、保存或发送数据`)
                    if (action.tone === "primary" || dismissOnly) closeDetail()
                  }}
                >
                  {action.label}
                  {action.tone === "primary" && <ChevronRight size={15} />}
                </button>
              ))}
            </footer>
          </section>
        </div>
      )}
      {confirm && (
        <div className="overlay-backdrop confirm-backdrop" role="presentation">
          <section
            className="confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
          >
            <span className="confirm-icon">
              <Info size={20} />
            </span>
            <div>
              <h2 id="confirm-title">{confirm.title}</h2>
              <p>{confirm.description}</p>
            </div>
            <footer>
              <button onClick={() => setConfirm(null)}>取消</button>
              <button
                className="primary"
                onClick={() => {
                  confirm.onConfirm()
                  setConfirm(null)
                }}
              >
                {confirm.confirmLabel || "确认"}
              </button>
            </footer>
          </section>
        </div>
      )}
      {toast && (
        <div className="toast" role="status" aria-live="polite">
          <CheckCircle2 size={17} />
          {toast}
        </div>
      )}
    </UiFeedbackContext.Provider>
  )
}

export function useUiFeedback() {
  const value = useContext(UiFeedbackContext)
  if (!value) throw new Error("UiFeedbackStore is required")
  return value
}
