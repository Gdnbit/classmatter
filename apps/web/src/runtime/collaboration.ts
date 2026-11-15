import { ApiError, workspace, type Session } from './api'
import { collaborationState, collaborationInvitation, collaborationPeer } from './workspace-chat-validators.cjs'

export type Peer = { peer_id: string; name: string; endpoint: string; public_key: string; class_id: string; term_id: string; status: 'active' | 'revoked'; version: number }
export type Invitation = { kind: 'classmatter.collaboration-invite.v1'; workspace_id: string; name: string; endpoint: string; public_key: string }
export type MaterialItem = { message_id: string; request_id: string; peer_id: string; direction: 'incoming' | 'outgoing'; operation: 'request' | 'material';
  title: string; body: string; source_document_id: string | null; source_version: number | null; class_id: string; term_id: string; thread_id: string;
  created_at: string; delivered_at: string | null; peer_name: string;
  status: 'queued' | 'retry-needed' | 'delivered' | 'received' | 'material-received' | 'material-sent' | 'saved';
  saved: { request_id: string; document_id: string; document_version: number } | null }
export type CollaborationState = { schema_version: 'classmatter.collaboration-state.v1'; peers: Peer[]; items: MaterialItem[] }

export function collaborationClient(session: Session) {
  const base = `${workspace(session)}/collaboration`
  async function read<T>(url: string, validate: (value: unknown) => boolean, body?: unknown, signal?: AbortSignal): Promise<T> {
    const response = await fetch(url, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal,
      headers: { 'x-class-os-csrf': session.csrf_token, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body) })
    if (!response.ok) throw new ApiError(response.status, response.headers.get('x-request-id') || '')
    const value: unknown = await response.json()
    if (!validate(value)) throw new Error('暂时无法更新协作事项，请重试。')
    return value as T
  }
  return {
    state: (thread?: string, signal?: AbortSignal) => read<CollaborationState>(base + (thread ? `/threads/${encodeURIComponent(thread)}` : ''), collaborationState, undefined, signal),
    invitation: (name: string) => read<{ invitation: Invitation }>(`${base}/invitation`, collaborationInvitation, { name }),
    add: (invitation: unknown, classroom: { class_id: string; term_id: string }) => read<Peer>(`${base}/peers`, collaborationPeer, { invitation, class_id: classroom.class_id, term_id: classroom.term_id }),
    revoke: (peer: Peer) => read<Peer>(`${base}/peers/${encodeURIComponent(peer.peer_id)}/revoke`, collaborationPeer, { expected_version: peer.version }),
    retry: (message: string) => read<CollaborationState>(`${base}/messages/${encodeURIComponent(message)}/retry`, collaborationState, {}),
  }
}
