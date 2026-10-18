import type { ActiveSurfaceStack } from "@/types/nav"

import type { DomainId, SurfaceId } from "@/types/surfaceIds"

const page = (
  domain: DomainId,
  rootSurfaceId: SurfaceId,
  extra: Partial<ActiveSurfaceStack> = {},
): ActiveSurfaceStack => ({
  domain,
  rootSurfaceId,
  modeSurfaceIds: [],
  params: {},
  ...extra,
})

export const defaultStack = (): ActiveSurfaceStack =>
  page("conversation", "HOME-CONVERSATION-IDLE")

export function parseUrl(url: string): ActiveSurfaceStack {
  const u = new URL(url, window.location.origin),
    p = u.pathname,
    view = u.searchParams.get("view")
  if (p === "/students")
    return page("students", "STUDENT-LIST", {
      viewSurfaceId:
        view === "seat"
          ? "VIEW-SEAT"
          : view === "dorm"
            ? "VIEW-DORM"
            : view === "group"
              ? "VIEW-GROUP"
              : "VIEW-LIST",
    })
  if (p.startsWith("/students/")) {
    const tabs: Record<string, SurfaceId> = {
      timeline: "STUDENT-DETAIL-TIMELINE",
      tasks: "STUDENT-DETAIL-TASKS",
      records: "STUDENT-DETAIL-RECORDS",
      grades: "STUDENT-DETAIL-GRADES",
      files: "STUDENT-DETAIL-FILES",
      relations: "STUDENT-DETAIL-RELATIONS",
    }
    return page("students", "STUDENT-DETAIL-OVERVIEW", {
      subpageSurfaceId: tabs[u.searchParams.get("tab") || ""],
      params: { studentId: p.split("/")[2] },
    })
  }
  if (p.startsWith("/data/spreadsheets/"))
    return page("data", "SPREADSHEET-WORKSPACE", {
      params: { fileId: p.split("/")[3] },
    })
  if (p.startsWith("/data/documents/"))
    return page("data", "DOCUMENT-WORKSPACE", {
      params: { fileId: p.split("/")[3] },
    })
  if (p.startsWith("/spaces/"))
    return page("work", "WORKSPACE-OVERVIEW", {
      params: { workspaceId: p.split("/")[2] },
    })
  if (p.startsWith("/settings"))
    return page(
      "settings",
      p === "/settings/user"
        ? "SETTINGS-USER-SECURITY"
        : "SETTINGS-USER-SECURITY",
    )
  const map: Record<string, [DomainId, SurfaceId]> = {
    "/dashboard": ["dashboard", "DASHBOARD-MAIN"],
    "/work": ["work", "WORK-TASKS"],
    "/data": ["data", "DATA-FILES"],
    "/inbox": ["inbox", "REVIEW-INBOX"],
    "/automation": ["automation", "AUTOMATION-PLANS"],
    "/knowledge": ["knowledge", "KNOWLEDGE-LIBRARY"],
    "/reports": ["reports", "REPORTS-LIST"],
  }
  return map[p] ? page(...map[p]) : defaultStack()
}
export function serializeStack(s: ActiveSurfaceStack): string {
  if (s.rootSurfaceId === "STUDENT-LIST")
    return `/students${
      s.viewSurfaceId && s.viewSurfaceId !== "VIEW-LIST"
        ? `?view=${s.viewSurfaceId.replace("VIEW-", "").toLowerCase()}`
        : ""
    }`
  if (s.rootSurfaceId === "STUDENT-DETAIL-OVERVIEW") {
    const tabs: Partial<Record<SurfaceId, string>> = {
      "STUDENT-DETAIL-TIMELINE": "timeline",
      "STUDENT-DETAIL-TASKS": "tasks",
      "STUDENT-DETAIL-RECORDS": "records",
      "STUDENT-DETAIL-GRADES": "grades",
      "STUDENT-DETAIL-FILES": "files",
      "STUDENT-DETAIL-RELATIONS": "relations",
    }
    const tab = s.subpageSurfaceId ? tabs[s.subpageSurfaceId] : undefined
    return `/students/${s.params.studentId}${tab ? `?tab=${tab}` : ""}`
  }
  if (s.rootSurfaceId === "SPREADSHEET-WORKSPACE")
    return `/data/spreadsheets/${s.params.fileId || "score-001"}`
  if (s.rootSurfaceId === "DOCUMENT-WORKSPACE")
    return `/data/documents/${s.params.fileId || "parents-001"}`
  if (s.rootSurfaceId === "WORKSPACE-OVERVIEW")
    return `/spaces/${s.params.workspaceId || "midterm"}`
  const paths: Partial<Record<SurfaceId, string>> = {
    "DASHBOARD-MAIN": "/dashboard",
    "WORK-TASKS": "/work",
    "DATA-FILES": "/data",
    "REVIEW-INBOX": "/inbox",
    "AUTOMATION-PLANS": "/automation",
    "KNOWLEDGE-LIBRARY": "/knowledge",
    "REPORTS-LIST": "/reports",
    "SETTINGS-USER-SECURITY": "/settings/user",
  }
  return paths[s.rootSurfaceId] || "/"
}
export const push = (stack: ActiveSurfaceStack) =>
  window.history.pushState({}, "", serializeStack(stack))

export const initPopstateListener = (
  dispatch: (stack: ActiveSurfaceStack) => void,
) => {
  const listener = () => dispatch(parseUrl(window.location.href))
  window.addEventListener("popstate", listener)
  return () => window.removeEventListener("popstate", listener)
}
