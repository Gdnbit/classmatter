import type { Activity } from "./api.ts"

// Relative to the authorized server snapshot, not the teacher's wall clock.
// This only requests a new QG projection: the server remains overdue authority.
export function deadlineRefreshDelay(activity: Activity): number | null {
  const asOf = Date.parse(activity.as_of)
  if (!Number.isFinite(asOf)) return null
  const nearest = activity.tasks.reduce((nearest, task) => {
    if (task.overdue || task.status === "done" || task.status === "cancelled" || task.due_at === null) return nearest
    const due = Date.parse(task.due_at)
    return Number.isFinite(due) ? Math.min(nearest, due) : nearest
  }, Infinity)
  if (!Number.isFinite(nearest)) return null
  // Minimum bounds near-boundary reads; maximum avoids browser timer overflow.
  return Math.min(2147483647, Math.max(5000, nearest - asOf + 250))
}

// Event/deadline invalidation only: no recurring hidden polling, writes, model
// calls or persistence. A failed read is not autonomously retried.
export function createQueryRefresh(options: {
  read: () => Promise<void>
  invalidate: () => void
  fail: (reason: unknown) => void
  available: () => boolean
  idle: () => boolean
  now: () => number
  schedule: (callback: () => void, delay: number) => unknown
  cancel: (timer: unknown) => void
}) {
  let disposed = false
  let requested = false
  let running = false
  let timer: unknown = null
  let lastStart = -Infinity

  function clear() {
    if (timer !== null) options.cancel(timer)
    timer = null
  }
  function resume() {
    if (disposed || !requested || running || !options.available() || !options.idle()) {
      clear()
      return
    }
    if (timer !== null) return
    // Debounce a foreground event burst, and bound repeated audited queries.
    timer = options.schedule(() => {
      timer = null
      if (disposed || !requested || running || !options.available() || !options.idle()) return
      requested = false
      running = true
      lastStart = options.now()
      void (async () => {
        try { await options.read() }
        catch (reason) { if (!disposed) options.fail(reason) }
        finally {
          running = false
          // A failed read is not automatically retried. Only a new event can
          // request another attempt; events during this read coalesce once.
          resume()
        }
      })()
    }, Math.max(250, lastStart + 5000 - options.now()))
  }
  return {
    request() { if (!disposed) { requested = true; resume() } },
    offline() {
      if (disposed) return
      requested = true
      clear()
      options.invalidate()
    },
    resume,
    dispose() { disposed = true; requested = false; clear() },
  }
}
