import type { Proposal } from "./api"
import { R1Dialog } from "./R1Dialog"
import { previewFields, userMessage } from "./user-facing"
import { SeatLayoutPreview } from './SeatLayoutPreview'
import { ChangeComparison } from './ChangeComparison'
import type { ChangePreview } from './workspace-chat'

type Props = {
  proposal: Proposal & { change_preview?: ChangePreview | null }
  error: string
  busy: boolean
  names?: Record<string, string>
  onReject: () => void
  onCheck: () => void
  onCommit: () => void
}

// Presentation only: no request client, identity, approval or persistence state.
export function CommandPreview({ proposal, error, busy, names, onReject, onCheck, onCommit }: Props) {
  return <R1Dialog titleId="r1-preview-title" busy={busy} onDismiss={onReject}>
    <h2 id="r1-preview-title">确认这次变更</h2>
    {error && <p className="r1-error" role="alert">{userMessage(error)}</p>}
    <p>
      请核对以下内容后确认。
      有效至 {new Date(proposal.expires_at).toLocaleString("zh-CN", { hour12: false })}
    </p>
    {proposal.change_preview ? <ChangeComparison preview={proposal.change_preview} /> : <dl>{previewFields(proposal.payload, names).map(([label, value], index) => <div key={index}>
      <dt>{label}</dt><dd>{value}</dd>
    </div>)}</dl>}
    {!proposal.change_preview && proposal.payload.command === 'seat.layout.create' && <SeatLayoutPreview rows={proposal.payload.rows} columns={proposal.payload.columns} />}
    <div className="r1-toolbar">
      <button disabled={busy} onClick={onReject}>放弃变更</button>
      <button disabled={busy} onClick={onCheck}>核对提交结果</button>
      <button className="r1-primary" disabled={busy} onClick={onCommit}>
        {busy ? "正在处理…" : proposal.risk === "W2" ? "明确批准并提交" : "确认提交"}
      </button>
    </div>
    <p className="r1-muted">若未看到结果，请先核对，避免重复保存。</p>
  </R1Dialog>
}
