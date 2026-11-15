import { useEffect, useRef, useState } from 'react'
import type { Classroom, Session } from './api'
import { collaborationClient, type Invitation, type MaterialItem, type Peer } from './collaboration'

export function CollaborationSettings({ session, classroom, disabled, onError }: {
  session: Session; classroom: Classroom | null; disabled: boolean; onError: (error: unknown) => void
}) {
  const [peers, setPeers] = useState<Peer[]>([]), [name, setName] = useState(''), [pasted, setPasted] = useState('')
  const [invitation, setInvitation] = useState<Invitation | null>(null), [adding, setAdding] = useState(false)
  const [checked, setChecked] = useState<Invitation | null>(null), [revoking, setRevoking] = useState<Peer | null>(null)
  const [busy, setBusy] = useState(false), [status, setStatus] = useState('')
  const active = useRef(true)
  useEffect(() => {
    active.current = true
    const abort = new AbortController()
    void collaborationClient(session).state(undefined, abort.signal).then(value => { if (active.current) setPeers(value.peers) }).catch(error => { if (!abort.signal.aborted) onError(error) })
    return () => { active.current = false; abort.abort() }
  }, [session.csrf_token])
  async function act(operation: () => Promise<void>) {
    if (busy || disabled) return
    setBusy(true); setStatus('')
    try { await operation() } catch (error) { if (active.current) onError(error) }
    finally { if (active.current) setBusy(false) }
  }
  const blocked = busy || disabled
  return <section className="r1-card" aria-label="同事协作">
    <h2>同事协作</h2>
    <label>我的称呼<input aria-label="我的称呼" value={name} maxLength={80} onChange={event => setName(event.target.value)} disabled={blocked} /></label>
    <div className="r1-toolbar">
      <button disabled={blocked || !name.trim()} onClick={() => void act(async () => {
        const value = await collaborationClient(session).invitation(name.trim())
        if (active.current) setInvitation(value.invitation)
      })}>生成协作邀请</button>
      <button disabled={blocked || !classroom || classroom.status === 'archived'} onClick={() => setAdding(value => !value)}>添加同事</button>
    </div>
    {invitation && <div>
      <label>协作邀请<textarea aria-label="协作邀请" readOnly value={JSON.stringify(invitation)} /></label>
      <button disabled={blocked} onClick={() => void act(async () => { await navigator.clipboard.writeText(JSON.stringify(invitation)); if (active.current) setStatus('已复制邀请') })}>复制邀请</button>
    </div>}
    {adding && <div>
      <label>同事的邀请<textarea aria-label="同事的邀请" value={pasted} maxLength={2000} disabled={blocked}
        onChange={event => { setPasted(event.target.value); setChecked(null) }} /></label>
      {!checked ? <button disabled={blocked || !pasted.trim()} onClick={() => {
        try {
          const value: unknown = JSON.parse(pasted)
          if (!value || typeof value !== 'object' || !('name' in value) || typeof value.name !== 'string' || !value.name.trim()) throw new Error('请粘贴完整的协作邀请。')
          setChecked(value as Invitation)
        } catch { onError(new Error('请粘贴完整的协作邀请。')) }
      }}>核对同事</button> : <div className="r1-toolbar"><strong>{checked.name}</strong>
        <button disabled={blocked || !classroom} title="双方确认联系后，可互相发送材料请求；文档发送前仍由你确认。" onClick={() => void act(async () => {
          if (!classroom) return
          await collaborationClient(session).add(checked, classroom)
          const state = await collaborationClient(session).state()
          if (active.current) { setPeers(state.peers); setChecked(null); setPasted(''); setAdding(false); setStatus('已添加同事') }
        })}>确认添加</button></div>}
    </div>}
    {peers.map(peer => <div className="r1-toolbar" key={peer.peer_id}><span>{peer.name}</span>
      {peer.status === 'revoked' ? <span>已停止协作</span> : <button disabled={blocked} onClick={() => setRevoking(peer)}>停止协作</button>}</div>)}
    {revoking && <div role="group" aria-label="确认停止协作"><p>停止与{revoking.name}协作？排队内容将停止发送，历史记录保留。</p>
      <button disabled={blocked} onClick={() => setRevoking(null)}>取消</button>
      <button disabled={blocked} onClick={() => void act(async () => {
        const value = await collaborationClient(session).revoke(revoking)
        if (active.current) { setPeers(items => items.map(peer => peer.peer_id === value.peer_id ? value : peer)); setRevoking(null) }
      })}>确认停止</button></div>}
    <span role="status">{status}</span>
  </section>
}

export function CollaborationThread({ session, thread }: { session: Session; thread: string }) {
  const [items, setItems] = useState<MaterialItem[]>([]), [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)
  const [retrying, setRetrying] = useState(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const abort = new AbortController(); let pending = false
    setItems([]); setFailed(false)
    async function update() {
      if (pending || abort.signal.aborted) return
      pending = true
      try { const value = await collaborationClient(session).state(thread, abort.signal); if (!abort.signal.aborted) { setItems(value.items.filter(item => item.operation === 'request')); setFailed(false) } }
      catch { if (!abort.signal.aborted) setFailed(true) }
      finally { pending = false }
    }
    void update()
    const timer = setInterval(() => void update(), 8000)
    return () => { abort.abort(); clearInterval(timer) }
  }, [session.csrf_token, thread, retry])
  const labels = { queued: '等待发送', 'retry-needed': '发送未完成', delivered: '等待补充', received: '待提供材料', 'material-received': '材料已收到', 'material-sent': '材料已发送', saved: '小结已保存' }
  if (!items.length && !failed) return null
  return <section aria-label="材料协作">
    {items.map(item => <div className="r1-toolbar" key={item.request_id}><strong>{item.title}</strong><span>{item.peer_name}</span><span role="status">{labels[item.status]}</span>
      {item.status === 'retry-needed' && <button disabled={retrying} onClick={() => {
        setRetrying(true)
        void collaborationClient(session).retry(item.message_id)
          .then(() => { if (mounted.current) setRetry(value => value + 1) })
          .catch(() => { if (mounted.current) setFailed(true) })
          .finally(() => { if (mounted.current) setRetrying(false) })
      }}>重试发送</button>}</div>)}
    {failed && <button onClick={() => setRetry(value => value + 1)}>重新读取协作事项</button>}
  </section>
}

export function CollaborationWaiting({ session, onSelect }: { session: Session; onSelect: (thread: string) => void }) {
  const [items, setItems] = useState<MaterialItem[]>([])
  useEffect(() => {
    const abort = new AbortController(); let pending = false
    async function update() {
      if (pending || abort.signal.aborted) return
      pending = true
      try {
        const value = await collaborationClient(session).state(undefined, abort.signal)
        if (!abort.signal.aborted) setItems(value.items.filter(item => item.operation === 'request' && item.direction === 'outgoing'
          && ['queued', 'delivered', 'retry-needed'].includes(item.status)))
      } catch { /* Existing thread retains its visible delivery status and recovery action. */ }
      finally { pending = false }
    }
    void update(); const timer = setInterval(() => void update(), 8000)
    return () => { abort.abort(); clearInterval(timer) }
  }, [session.csrf_token])
  return <>{items.map(item => <button className="r1-attention-item" key={item.request_id} onClick={() => onSelect(item.thread_id)}>
    <span>{item.title} · {item.peer_name}</span><span aria-hidden="true">›</span>
  </button>)}</>
}
