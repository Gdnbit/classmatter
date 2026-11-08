import type { WorkFilter } from "./work-projection.ts"

export type RuntimePage = "conversation" | "dashboard" | "students" | "work" | "documents" | "settings" | "unavailable"
export type StudentTab = "overview" | "timeline" | "tasks" | "records" | "unavailable"
export type RuntimeRoute = {
  conversationId: string
  conversationClassId: string
  conversationTermId: string
  page: RuntimePage
  studentId: string
  taskId: string
  documentId: string
  workFilter: WorkFilter
  studentView: "list" | "table"
  studentTab: StudentTab
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export const runtimeRoute = (page: RuntimePage = "conversation"): RuntimeRoute => ({
  conversationId: "", conversationClassId: "", conversationTermId: "",
  page, studentId: "", taskId: "", documentId: "", workFilter: "all", studentView: "list", studentTab: "overview",
})

// Presentation hints only. Entity IDs must still resolve in authorized QG data.
// Never import Demo paths/objects, accept history.state, or preserve free text.
export function parseRuntimeRoute(path: string): RuntimeRoute {
  const unavailable = () => runtimeRoute("unavailable")
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\") || path.length > 1024 || /[\u0000-\u001f]/.test(path)) return unavailable()
  const url = new URL(path, "https://classmatter.invalid")
  if (url.origin !== "https://classmatter.invalid" || url.pathname !== path.split(/[?#]/)[0]) return unavailable()
  const single = (key: string) => url.searchParams.getAll(key).length <= 1
  if (!["view", "tab", "student", "task", "filter"].every(single)) return unavailable()
  const simple: Record<string, RuntimePage> = {
    "/": "conversation", "/dashboard": "dashboard", "/settings": "settings",
    "/settings/user": "settings", "/unavailable": "unavailable",
  }
  if (simple[url.pathname]) return runtimeRoute(simple[url.pathname])
  if (url.pathname === "/data" && !url.search && !url.hash) return runtimeRoute("documents")
  const document = url.pathname.match(/^\/data\/documents\/([^/]+)$/)
  if (document) {
    if (url.search || url.hash || (document[1] !== "new" && !uuid.test(document[1]))) return unavailable()
    return { ...runtimeRoute("documents"), documentId: document[1].toLowerCase() }
  }
  const conversation = url.pathname.match(/^\/conversations\/([^/]+)\/([^/]+)\/([^/]+)$/)
  const workspaceChat = url.pathname.match(/^\/chats\/([^/]+)$/)
  if (workspaceChat) {
    if (url.search || url.hash || !uuid.test(workspaceChat[1])) return unavailable()
    return { ...runtimeRoute(), conversationId: workspaceChat[1].toLowerCase() }
  }
  if (conversation) {
    if (url.search || url.hash || !conversation.slice(1).every(value => uuid.test(value))) return unavailable()
    return { ...runtimeRoute(), conversationClassId: conversation[1].toLowerCase(),
      conversationTermId: conversation[2].toLowerCase(), conversationId: conversation[3].toLowerCase() }
  }
  if (url.pathname === "/students") {
    const view = url.searchParams.get("view") || "list"
    if (view !== "list" && view !== "table") return unavailable()
    return { ...runtimeRoute("students"), studentView: view }
  }
  const detail = url.pathname.match(/^\/students\/([^/]+)$/)
  if (detail) {
    if (!uuid.test(detail[1])) return unavailable()
    const tab = url.searchParams.get("tab") || "overview"
    const view = url.searchParams.get("view") || "list"
    if (view !== "list" && view !== "table") return unavailable()
    const studentTab = ["overview", "timeline", "tasks", "records"].includes(tab) ? tab as StudentTab : "unavailable"
    return { ...runtimeRoute("students"), studentId: detail[1].toLowerCase(), studentTab, studentView: view }
  }
  if (url.pathname === "/work") {
    const studentId = url.searchParams.get("student") || "", taskId = url.searchParams.get("task") || ""
    const filter = url.searchParams.get("filter") || "all"
    if ((studentId && !uuid.test(studentId)) || (taskId && !uuid.test(taskId)) || !["all", "open", "mine", "waiting", "closed"].includes(filter)) return unavailable()
    return { ...runtimeRoute("work"), studentId: studentId.toLowerCase(), taskId: taskId.toLowerCase(), workFilter: filter as WorkFilter }
  }
  return unavailable()
}

export function runtimePath(route: RuntimeRoute): string {
  if (route.page === "documents") return !route.documentId ? "/data"
    : route.documentId === "new" || uuid.test(route.documentId) ? `/data/documents/${route.documentId}` : "/unavailable"
  if (route.page === "conversation" && route.conversationId) {
    if (!route.conversationClassId && !route.conversationTermId) return uuid.test(route.conversationId) ? `/chats/${route.conversationId}` : "/unavailable"
    return [route.conversationClassId, route.conversationTermId, route.conversationId].every(value => uuid.test(value))
      ? `/conversations/${route.conversationClassId}/${route.conversationTermId}/${route.conversationId}` : "/unavailable"
  }
  if (route.page === "students") {
    if (route.studentId) {
      const query = new URLSearchParams()
      if (route.studentView === "table") query.set("view", "table")
      if (route.studentTab !== "overview") query.set("tab", route.studentTab)
      return `/students/${route.studentId}${query.size ? `?${query}` : ""}`
    }
    return route.studentView === "table" ? "/students?view=table" : "/students"
  }
  if (route.page === "work") {
    const query = new URLSearchParams()
    if (route.studentId) query.set("student", route.studentId)
    if (route.taskId) query.set("task", route.taskId)
    if (route.workFilter !== "all") query.set("filter", route.workFilter)
    return `/work${query.size ? `?${query}` : ""}`
  }
  return route.page === "conversation" ? "/" : `/${route.page}`
}
