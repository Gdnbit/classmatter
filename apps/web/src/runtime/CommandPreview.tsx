import type { Proposal } from "./api"
import { R1Dialog } from "./R1Dialog"

type Props = {
  proposal: Proposal
  error: string
  busy: boolean
  onReject: () => void
  onCheck: () => void
  onCommit: () => void
}

// Presentation only: no request client, identity, approval or persistence state.
export function CommandPreview({ proposal, error, busy, onReject, onCheck, onCommit }: Props) {
  return <R1Dialog titleId="r1-preview-title" busy={busy} onDismiss={onReject}>
    <h2 id="r1-preview-title">确认这次变更</h2>
    {error && <p className="r1-error" role="alert">{error}</p>}
    <p>
      {proposal.risk === "W2" ? "需要你明确批准后才能提交。" : "请核对服务端预览，再明确提交。"}
      有效至 {new Date(proposal.expires_at).toLocaleString("zh-CN", { hour12: false })}
    </p>
    <dl>{Object.entries(proposal.payload).map(([key, value]) => <div key={key}>
      <dt>{key}</dt><dd>{value === null ? "无" : String(value)}</dd>
    </div>)}</dl>
    <details><summary>完整性摘要</summary>{proposal.payload_hash}</details>
    <div className="r1-toolbar">
      <button disabled={busy} onClick={onReject}>放弃变更</button>
      <button disabled={busy} onClick={onCheck}>核对提交结果（不重复写入）</button>
      <button className="r1-primary" disabled={busy} onClick={onCommit}>
        {busy ? "正在处理…" : proposal.risk === "W2" ? "明确批准并提交" : "确认提交"}
      </button>
    </div>
    <p className="r1-muted">结果未知时先核对原请求；确认未提交后可按原键重试，不要重复新建。</p>
  </R1Dialog>
}
