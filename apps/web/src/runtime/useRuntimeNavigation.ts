import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { parseRuntimeRoute, runtimePath, runtimeRoute, type RuntimeRoute } from "./navigation"

// Thin native-history adapter, not a domain store. No entity objects, search
// text, draft, cookie, credential or approval is placed in URL/history.state.
export function useRuntimeNavigation(blocked: boolean) {
  const [route, setRoute] = useState(() => parseRuntimeRoute(location.pathname + location.search))
  const [deferred, setDeferred] = useState(false)
  const current = useRef(route)
  const isBlocked = useRef(blocked)
  const pending = useRef<{ route: RuntimeRoute; mode: "push" | "replace" } | null>(null)
  const mode = useRef<"push" | "replace">("replace")
  current.current = route
  isBlocked.current = blocked

  function apply(next: RuntimeRoute, historyMode: "push" | "replace") {
    pending.current = null
    mode.current = historyMode
    current.current = next
    setDeferred(false)
    setRoute(next)
  }
  function change(patch: Partial<RuntimeRoute>) {
    const next = { ...(pending.current?.route || current.current), ...patch }
    if (isBlocked.current) {
      pending.current = { route: next, mode: "push" }
      setDeferred(true)
    } else apply(next, "push")
  }
  function clearTask() {
    // Trusted receipt adoption may clear a selection while a user navigation
    // remains deferred. It must not discard that destination or push history.
    mode.current = "replace"
    const next = { ...current.current, taskId: "" }
    current.current = next
    setRoute(next)
  }
  useLayoutEffect(() => {
    if (pending.current) return
    const path = runtimePath(route)
    if (mode.current === "replace") history.replaceState(null, "", path)
    else if (location.pathname + location.search + location.hash !== path) history.pushState(null, "", path)
    mode.current = "push"
  }, [route])
  useEffect(() => {
    const restore = () => {
      const next = parseRuntimeRoute(location.pathname + location.search)
      if (isBlocked.current) {
        // Keep the visible form/target unchanged; do not bounce history or
        // add entries. Apply the latest requested destination after it ends.
        pending.current = { route: next, mode: "replace" }
        setDeferred(true)
      } else apply(next, "replace")
    }
    window.addEventListener("popstate", restore)
    return () => window.removeEventListener("popstate", restore)
  }, [])
  useEffect(() => {
    if (!blocked && pending.current) apply(pending.current.route, pending.current.mode)
  }, [blocked, deferred])
  return {
    route, deferred,
    setPage: (page: RuntimeRoute["page"]) => change({ page }),
    setConversation: (classId: string, termId: string, conversationId: string) =>
      change({ page: "conversation", conversationClassId: classId, conversationTermId: termId, conversationId }),
    setSelectedStudent: (studentId: string) => change({ studentId, taskId: "", studentTab: "overview" }),
    setTaskId: (taskId: string) => change({ taskId }),
    setWorkFilter: (workFilter: RuntimeRoute["workFilter"]) => change({ workFilter }),
    setStudentView: (studentView: RuntimeRoute["studentView"]) => change({ studentView }),
    setStudentTab: (studentTab: RuntimeRoute["studentTab"]) => change({ studentTab }),
    reset: () => apply(runtimeRoute(), "replace"),
    clearTask,
    clearSelection: () => apply({ ...current.current, studentId: "", taskId: "", workFilter: "all", studentTab: "overview",
      conversationId: "", conversationClassId: "", conversationTermId: "" }, "replace"),
  }
}
