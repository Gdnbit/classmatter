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
        if (!state?.storage_available) throw new Error("暂时无法保存模型配置。")
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
        ? new Error("配置有误，请检查模型名称和服务地址。") : reason)
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
    <button disabled={disabled || pending} onClick={() => void refreshStatus()}>刷新模型状态</button>
    <p className="r1-muted">保存配置后，测试连接并启用模型。</p>
    {state && <p role="status" data-model-mode={state.mode} data-model-key-configured={state.key_configured} data-config-version={state.version}>模型状态：{state.mode === "configured-api" ? "已连接" : state.mode === "stale" ? "配置已更新，请重新测试并启用" : "未连接（示例模式）"}。{state.key_configured ? `当前模型：${state.configuration?.model}` : "尚未配置模型。"}{state.test_passed ? " 连接测试通过，可启用。" : ""}</p>}
    <form ref={formElement} onSubmit={event => void submit(event)} onChange={changed}>
      <label>API 协议<select name="protocol" aria-label="API 协议" defaultValue="responses" disabled={disabled || (!state && pending)}>
        <option value="responses">Responses</option><option value="chat-completions">Chat Completions</option>
      </select></label>
      <label>模型名称<input name="model" required maxLength={128} autoComplete="off" spellCheck={false} disabled={disabled || (!state && pending)} placeholder="填写供应商提供的准确模型名称" /></label>
      <label>API 基础地址<input name="base_url" type="url" required maxLength={512} autoComplete="off" spellCheck={false} disabled={disabled || (!state && pending)} placeholder="https://供应商域名/v1" /></label>
      <p className="r1-muted">请填写服务商提供的地址，密钥单独填写。</p>
      {state?.storage_available && <label>API 密钥<input ref={keyInput} name="api_key" type="password" maxLength={2048} autoComplete="off" disabled={disabled} /></label>}
      <button type="submit" disabled={disabled || pending}>{pending ? "正在校验格式…" : "检查配置"}</button>
      <button type="submit" value="save" disabled={disabled || pending || !state?.storage_available}>保存模型配置</button>
    </form>
    {result && <p role="status">格式检查通过，尚未保存。</p>}
    {!state?.storage_available && <p className="r1-muted">暂时无法保存或连接模型。</p>}
    {state?.key_configured && <>
      <p className="r1-muted">以下操作针对已保存配置：{state.configuration?.base_url}。{!state.network_permitted && "此地址暂不可连接。"}</p>
      <label className="r1-model-consent"><input type="checkbox" checked={confirmed} disabled={pending || disabled} onChange={event => setConfirmed(event.target.checked)} />我了解连接测试可能产生费用</label>
      <div className="r1-toolbar">
        <button disabled={disabled || pending || !confirmed || !state.network_permitted} onClick={() => void operate("test")}>测试已保存连接（可能计费）</button>
        <button disabled={disabled || pending || !confirmed || !state.test_passed || !state.network_permitted} onClick={() => void operate("enable")}>启用模型</button>
        <button disabled={disabled || pending} onClick={() => void onPreview({ command: "model_configuration.clear", candidate_id: crypto.randomUUID(), expected_version: state.version, protocol: null, model: null, base_url: null })}>预览移除已保存配置</button>
      </div>
    </>}
    {state && state.mode !== "offline" && <button disabled={disabled || pending} onClick={() => void operate("disable")}>断开模型连接</button>}
  </details>
}
