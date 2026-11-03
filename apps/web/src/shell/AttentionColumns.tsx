import type { ReactNode } from "react"

export function AttentionColumns({ children, compact = false, className = "" }: {
  children: readonly [ReactNode, ReactNode, ReactNode]; compact?: boolean; className?: string
}) {
  return <div className={`ambient${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}>
    {(["需要我处理", "可能遗漏", "等待别人"] as const).map((label, index) =>
      <section key={label}><h3>{label}</h3>{children[index]}</section>)}
  </div>
}
