import * as validators from "./identity-validators.cjs"
import { ApiError, request, type Session } from "./api"

type IdentityReplies = {
  challenge: Pick<Session, "schema_version" | "csrf_token">
  session: Omit<Session, "recovery_codes">
  kit: Session & { recovery_codes: string[] }
  signedOut: { schema_version: "class-os.identity.v1"; status: "signed_out" | "signed_out_all" }
  logoutReceipt: { schema_version: "class-os.identity-logout-receipt.v1"; request_id: string; action: "logout"; status: "committed" | "not_committed" }
  operationReceipt: { schema_version: "class-os.identity-operation-receipt.v1"; request_id: string; action: string; status: "committed"; result_replayable: false }
}
type Kind = keyof IdentityReplies
const routes: Record<string, readonly [Kind, boolean]> = {
  "/api/identity/context": ["challenge", false],
  "/api/identity/session": ["session", false],
  "/api/identity/bootstrap": ["kit", true],
  "/api/identity/login": ["session", true],
  "/api/identity/reauthenticate": ["session", true],
  "/api/identity/logout": ["signedOut", true],
  "/api/identity/logout-all": ["signedOut", true],
  "/api/identity/recovery/exchange": ["challenge", true],
  "/api/identity/recovery/complete": ["kit", true],
  "/api/identity/recovery/reissue": ["kit", true],
}
const operationActions: Record<string, string> = {
  "/api/identity/bootstrap": "bootstrap", "/api/identity/login": "login",
  "/api/identity/reauthenticate": "reauthenticate", "/api/identity/logout-all": "logout_all",
  "/api/identity/recovery/exchange": "recovery_exchange", "/api/identity/recovery/complete": "recovery_complete",
  "/api/identity/recovery/reissue": "recovery_reissue",
}

export class IdentityResponseInvalid extends Error {
  constructor() { super("身份响应契约不匹配，未采纳。请核对本机服务。") }
}
export class IdentityOutcomeUnknown extends Error {
  constructor(committed = false) { super((committed ? "原身份操作已提交，但响应交付未确认；原 token 和一次性恢复码不能补发。" : "身份操作结果暂时无法确认，可能已经生效。") + "请勿连续重复操作；先只读核对登录状态，或用已知密码登录。重置后尝试刚设置的新密码；恢复访问兑换失败时原码可能已使用，可选择另一枚未使用码。如未收到新恢复码，登录后再明确重新签发。") }
}

export function decodeIdentity<K extends Kind>(kind: K, data: unknown): IdentityReplies[K] {
  if (!Object.prototype.hasOwnProperty.call(validators, kind)) throw new IdentityResponseInvalid()
  const validate = validators[kind]
  const valid = validate(data)
  validate.errors = null // Do not retain schema-error details across identities.
  if (!valid) throw new IdentityResponseInvalid()
  if (kind === "kit") {
    const codes = (data as IdentityReplies["kit"]).recovery_codes
    if (new Set(codes.map(code => code.split(".", 1)[0])).size !== 5) throw new IdentityResponseInvalid()
  }
  return data as IdentityReplies[K]
}

export async function identityRequest<K extends Kind>(kind: K, path: string, body?: unknown, csrf?: string): Promise<IdentityReplies[K]> {
  if (!Object.prototype.hasOwnProperty.call(routes, path) || routes[path][0] !== kind || routes[path][1] !== (body !== undefined)) {
    throw new IdentityResponseInvalid()
  }
  const action = operationActions[path]
  let requestId = ""
  if (action) {
    if (!body || typeof body !== "object" || Array.isArray(body) || Object.prototype.hasOwnProperty.call(body, "request_id")) throw new IdentityResponseInvalid()
    requestId = crypto.randomUUID()
    body = { ...body, request_id: requestId }
  }
  try {
    return decodeIdentity(kind, await request<unknown>(path, body, csrf))
  } catch (reason) {
    if (body !== undefined && (!(reason instanceof ApiError) || reason.status >= 500 || reason.status === 409)) {
      let committed = false
      if (action) {
        try {
          const receipt = decodeIdentity("operationReceipt", await request<unknown>(
            `/api/identity/receipts/${action}/${requestId}`, undefined, csrf))
          committed = receipt.request_id === requestId && receipt.action === action
        } catch { /* No capability or success inferred from a failed lookup. */ }
      }
      if (committed && path === "/api/identity/logout-all") {
        return decodeIdentity("signedOut", { schema_version: "class-os.identity.v1", status: "signed_out_all" }) as IdentityReplies[K]
      }
      throw new IdentityOutcomeUnknown(committed)
    }
    throw reason
  }
}

export async function logoutIdentity(csrf: string): Promise<IdentityReplies["signedOut"]> {
  const requestId = crypto.randomUUID()
  try {
    return await identityRequest("signedOut", "/api/identity/logout", { request_id: requestId }, csrf)
  } catch (reason) {
    if (!(reason instanceof IdentityOutcomeUnknown)) throw reason
    try {
      // Reconcile only. Never repeat a mutation or recover an identity capability.
      const receipt = decodeIdentity("logoutReceipt", await request<unknown>(
        `/api/identity/logout/receipts/${requestId}`, undefined, csrf))
      if (receipt.request_id === requestId && receipt.status === "committed") {
        return { schema_version: "class-os.identity.v1", status: "signed_out" }
      }
    } catch { /* Unavailable/unbound receipt is not proof of success. */ }
    throw reason
  }
}
