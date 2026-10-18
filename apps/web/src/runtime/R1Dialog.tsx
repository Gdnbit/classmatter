import { useLayoutEffect, useRef, type ReactNode } from "react"

/** Browser-owned modal focus/inert behavior; never approves a business write. */
export function R1Dialog({ titleId, children, onDismiss, busy = false, returnFocusTo }: {
  titleId: string
  children: ReactNode
  onDismiss?: () => void
  busy?: boolean
  returnFocusTo?: HTMLElement | null
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useLayoutEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const previous = returnFocusTo || document.activeElement
    dialog.showModal()
    return () => {
      if (dialog.open) dialog.close()
      if (previous instanceof HTMLElement && previous.isConnected && !previous.matches(":disabled")) previous.focus()
    }
  }, [])
  return <dialog ref={ref} className="r1-modal" aria-labelledby={titleId} onKeyDown={event => {
    if (event.key !== "Tab") return
    const dialog = event.currentTarget
    const controls = [...dialog.querySelectorAll<HTMLElement>("button,input,select,textarea,a[href],summary,[tabindex]")]
      .filter(element => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0)
    const target = event.shiftKey ? controls.at(-1) : controls[0]
    const boundary = event.shiftKey ? controls[0] : controls.at(-1)
    if (target && (document.activeElement === boundary || document.activeElement === dialog)) {
      // Native modality makes the background inert; keep Tab from moving to
      // browser chrome at the end of the modal's visible controls as well.
      event.preventDefault()
      target.focus()
    }
  }} onCancel={event => {
    event.preventDefault()
    if (!busy) onDismiss?.()
  }}><section className="r1-dialog">{children}</section></dialog>
}
