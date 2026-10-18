import { useEffect, useRef, useState, type FormEvent } from "react"
import { ApiError, type Session, type Command } from "./api"
import { getModelStatus, stageModel, modelControl, validateConfiguration, type ConfigurationResult, type ModelConfiguration, type ModelStatus } from "./model-configuration"

export function ModelConfigurationForm({ session, disabled, onError, onPreview, onModeChanged }: {
  session: Session; disabled: boolean; onError: (reason: unknown) => void
  onPreview: (command: Command) => Promise<void>; onModeChanged: (verified: boolean) => void
}) {
  const [pending, setPending] = useState(true)
  const [result, setResult] = useState<ConfigurationResult | null>(null)
  const [state, setState] = useState<ModelStatus | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const keyInput = useRef<HTMLInputElement | null>(null)
  const formElement = useRef<HTMLFormElement | null>(null)
  const generation = useRef(0)
  const running = useRef<AbortController | null>(null)
  useEffect(() => {
    const current = ++generation.current
    const controller = new AbortController(); running.current = controller
    setPending(true)
    void getModelStatus(session, controller.signal).then(value => {
      if (generation.current === current) {
        setState(value)
        if (value.configuration) for (const name of ["protocol", "model", "base_url"] as const) {
          const element = formElement.current?.elements.namedItem(name)
          if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement) element.value = value.configuration[name]
        }
      }
    }).catch(reason => { if (generation.current === current) onError(reason) })
      .finally(() => { if (generation.current === current) setPending(false) })
    return () => { generation.current++; controller.abort(); running.current?.abort() }
  }, [session.csrf_token])
  const changed = () => {
    generation.current++; running.current?.abort(); setPending(false); setResult(null)
    setConfirmed(false)
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const saving = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "save"
    const candidate: ModelConfiguration = {
      protocol: String(form.get("protocol")) as ModelConfiguration["protocol"],
      model: String(form.get("model")), base_url: String(form.get("base_url")),
    }
    const current = ++generation.current
    running.current?.abort()
    const controller = new AbortController(); running.current = controller
    setResult(null); setPending(true)
    try {
      if (saving) {
        if (!state?.storage_available) throw new Error("当前运行不支持受保护的模型凭据存储。")
        const secret = String(form.get("api_key") || "")
        if (keyInput.current) keyInput.current.value = ""
        const command = await stageModel(session, candidate, secret, state.version, controller.signal)
        if (generation.current === current) await onPreview(command)
      } else {
        const value = await validateConfiguration(session, candidate, controller.signal)
        if (generation.current === current) setResult(value)
      }
    } catch (reason) {
      if (generation.current === current) onError(reason instanceof ApiError && reason.status === 400
        ? new Error("模型配置请求未通过，请核对名称、地址和当前版本；不要在地址中填写账号密码、查询参数或片段。没有自动保存或启用。") : reason)
    } finally {
      if (generation.current === current) { setPending(false); running.current = null }
    }
  }
  async function operate(operation: "test" | "enable" | "disable") {
    if (!state || pending || disabled || (operation !== "disable" && !confirmed)) return
    const current = ++generation.current
    running.current?.abort(); const controller = new AbortController(); running.current = controller
    setPending(true)
    // Closing/editing can abort delivery after the server accepted the control.
    // Keep Agent blocked until a validated result or explicit status check.
    onModeChanged(false)
    try {
      const value = await modelControl(session, operation, state, controller.signal)
      if (generation.current === current) {
        setState(value)
        onModeChanged(true)
      }
    } catch (reason) { if (generation.current === current) {
      onModeChanged(false)
      onError(reason instanceof ApiError && reason.status === 401 ? reason : new Error("模型操作结果未确认，可能已经生效或计费；请先核对模型状态，不要连续重复测试。"))
    } }
    finally { if (generation.current === current) setPending(false) }
  }
  async function refreshStatus() {
    const current = ++generation.current
    running.current?.abort(); const controller = new AbortController(); running.current = controller
    setPending(true)
    try {
      const value = await getModelStatus(session, controller.signal)
      if (current === generation.current) { setState(value); onModeChanged(true) }
    } catch (reason) { if (current === generation.current) onError(reason) }
    finally { if (current === generation.current) setPending(false) }
  }
  return <details className="r1-model-configuration" onToggle={event => {
    if (!event.currentTarget.open) { changed(); if (keyInput.current) keyInput.current.value = "" }
  }}>
    <summary>模型配置、连接与启用</summary>
    <button disabled={disabled || pending} onClick={() => void refreshStatus()}>核对模型状态（不联网）</button>
    <p className="r1-muted">保存、测试与启用是三个独立步骤。保存不会联网或启用；测试会访问已保存地址并可能计费，只验证合成工具协议，不证明业务质量。重启后回到离线，密钥不回显、不进入对话或核心导出包。</p>
    {state && <p role="status">模型运行：{state.mode === "configured-api" ? "已启用配置 API" : state.mode === "stale" ? "配置已变化，旧启用已失效；需重新测试/启用或关闭" : "离线合成模型"}；配置版本 {state.version}。{state.key_configured ? `已保护保存：${state.configuration?.model}` : "尚未保存密钥。"}{state.test_passed ? " 本会话工具协议测试通过（10分钟内可启用）。" : " 暂无有效测试结果。"}</p>}
    <form ref={formElement} onSubmit={event => void submit(event)} onChange={changed}>
      <label>API 协议<select name="protocol" aria-label="API 协议" defaultValue="responses" disabled={disabled || (!state && pending)}>
        <option value="responses">Responses</option><option value="chat-completions">Chat Completions</option>
      </select></label>
      <label>模型名称<input name="model" required maxLength={128} autoComplete="off" spellCheck={false} disabled={disabled || (!state && pending)} placeholder="填写供应商提供的准确模型名称" /></label>
      <label>API 基础地址<input name="base_url" type="url" required maxLength={512} autoComplete="off" spellCheck={false} disabled={disabled || (!state && pending)} placeholder="https://供应商域名/v1" /></label>
      <p className="r1-muted">地址不得包含账号密码、查询参数或片段；不要将密钥放入地址。格式检查不联网。只有启动时显式允许的精确地址才能测试或启用。</p>
      {state?.storage_available && <label>API 密钥<input ref={keyInput} name="api_key" type="password" maxLength={2048} autoComplete="off" disabled={disabled} /></label>}
      <button type="submit" disabled={disabled || pending}>{pending ? "正在校验格式…" : "校验配置格式（不联网）"}</button>
      <button type="submit" value="save" disabled={disabled || pending || !state?.storage_available}>预览保存模型配置（不联网）</button>
    </form>
    {result && <p role="status">配置格式通过；本次仅校验，未保存、未联网测试、未改变当前启用状态。</p>}
    {!state?.storage_available && <p className="r1-muted">当前宿主未提供受保护的凭据存储，保存和外部调用不可用；格式检查与直接业务 UI 仍可使用。</p>}
    {state?.key_configured && <>
      <p className="r1-muted">以下操作针对已保存配置：{state.configuration?.base_url}。{!state.network_permitted && "当前启动未允许该地址，不能测试或启用。"}</p>
      <label className="r1-model-consent"><input type="checkbox" checked={confirmed} disabled={pending || disabled} onChange={event => setConfirmed(event.target.checked)} />我确认访问此供应商并可能计费，仅用于合成数据验证</label>
      <div className="r1-toolbar">
        <button disabled={disabled || pending || !confirmed || !state.network_permitted} onClick={() => void operate("test")}>测试已保存连接（可能计费）</button>
        <button disabled={disabled || pending || !confirmed || !state.test_passed || !state.network_permitted} onClick={() => void operate("enable")}>启用已测试模型（本次启动）</button>
        <button disabled={disabled || pending} onClick={() => void onPreview({ command: "model_configuration.clear", candidate_id: crypto.randomUUID(), expected_version: state.version, protocol: null, model: null, base_url: null })}>预览移除已保存配置</button>
      </div>
    </>}
    {state && state.mode !== "offline" && <button disabled={disabled || pending} onClick={() => void operate("disable")}>关闭配置 API，恢复离线模型</button>}
  </details>
}
