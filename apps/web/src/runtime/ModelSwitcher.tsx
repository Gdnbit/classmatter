import { useEffect, useId, useRef, useState } from "react"
import { Check, ChevronDown, Settings } from "lucide-react"
import type { Command, Session } from "./api"
import { getModelStatus, modelControl, stageModelSwitch, type ModelStatus } from "./model-configuration"

export function ModelSwitcher({ session, state, revision, disabled, onManage, onPreview, onVerified, onError }: {
  session: Session; state: ModelStatus | null; revision: number; disabled: boolean;
  onManage: () => void; onPreview: (command: Command) => Promise<void>;
  onVerified: (verified: boolean) => void; onError: (error: unknown) => void;
}) {
  const [open, setOpen] = useState(false), [pending, setPending] = useState(false)
  const [model, setModel] = useState(""), [current, setCurrent] = useState(state)
  const [recent, setRecent] = useState<string[]>([])
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null)
  const generation = useRef(0), title = useId()
  useEffect(() => { setCurrent(state) }, [state])
  useEffect(() => {
    if (!current?.configuration) { setRecent([]); return }
    // Display preference only. Every selection still goes through server QG,
    // current-version checks, original BCG confirmation and provider testing.
    const key = `classmatter-model-history/${session.subject.workspace_id}/${current.configuration.protocol}/${current.configuration.base_url}`
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(key) || "[]")
      const previous = Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}$/.test(value)).slice(0, 8) : []
      const values = current.mode === "configured-api" ? [...new Set([current.configuration.model, ...previous])].slice(0, 8) : previous
      setRecent(values); localStorage.setItem(key, JSON.stringify(values))
    } catch { setRecent([]) }
  }, [session.subject.workspace_id, current?.configuration?.model, current?.configuration?.base_url, current?.configuration?.protocol, current?.mode])
  useEffect(() => {
    const version = ++generation.current, controller = new AbortController()
    void getModelStatus(session, controller.signal).then(value => {
      if (version === generation.current) setCurrent(value)
    }).catch(error => { if (!controller.signal.aborted) onError(error) })
    return () => { generation.current++; controller.abort() }
  }, [session.csrf_token, revision])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus() } }
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape)
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape) }
  }, [open])
  async function operate(operation: "switch" | "enable" | "refresh", targetModel = model.trim()) {
    if (pending || disabled) return
    const version = generation.current
    setPending(true)
    try {
      const value = await getModelStatus(session)
      if (version !== generation.current) return
      setCurrent(value)
      if (operation === "switch") {
        const command = await stageModelSwitch(session, value, targetModel)
        if (version !== generation.current) return
        setOpen(false); await onPreview(command)
      } else if (operation === "enable") {
        onVerified(false)
        const tested = await modelControl(session, "test", value)
        if (!tested.test_passed) throw new Error("模型检测未通过，未启用；请稍后核对状态")
        const enabled = await modelControl(session, "enable", tested)
        if (version !== generation.current) return
        setCurrent(enabled); onVerified(true); setOpen(false)
      } else { onVerified(true) }
    } catch (error) { if (version === generation.current) onError(error) }
    finally { if (version === generation.current) setPending(false) }
  }
  return <div className="r1-model-picker" ref={root}>
    <button ref={trigger} type="button" className="r1-model-trigger" aria-label="切换模型" aria-expanded={open}
      aria-controls={title} disabled={disabled || pending} onClick={() => setOpen(value => !value)}>
      <span>{pending ? "正在核对模型…" : current?.mode === "configured-api" ? current.configuration?.model : "选择模型"}</span><ChevronDown size={15} />
    </button>
    {open && <section id={title} className="r1-model-menu" aria-label="选择模型">
      <h3>选择模型</h3>
      {current?.configuration ? <>
        <div className="r1-current-model"><span><strong>{current.configuration.model}</strong><small>{current.mode === "configured-api" ? "当前已连接" : "尚未启用此配置"}</small></span>{current.mode === "configured-api" && <Check size={18} />}</div>
        {recent.some(value => value !== current.configuration?.model) && <div className="r1-recent-models"><p>最近使用</p>{recent.filter(value => value !== current.configuration?.model).map(value => <button type="button" key={value} disabled={pending || disabled} onClick={() => void operate("switch", value)}>{value}</button>)}</div>}
        <label>使用同一服务商的其他模型<input aria-label="切换后的模型名称" value={model} maxLength={128} placeholder="输入模型 ID" onChange={event => setModel(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); if (model.trim() && model.trim() !== current.configuration?.model) void operate("switch") } }} disabled={pending || disabled} /></label>
        <button type="button" disabled={pending || disabled || !model.trim() || model.trim() === current.configuration.model} onClick={() => void operate("switch")}>预览切换模型</button>
        {current.mode !== "configured-api" && <><p>测试将调用当前服务商，费用以服务商为准。</p><button type="button" disabled={pending || disabled} onClick={() => void operate("enable")}>测试并启用</button></>}
      </> : <p>尚未配置模型，可在模型设置中添加。</p>}
      <button type="button" disabled={pending || disabled} onClick={() => void operate("refresh")}>核对模型状态</button>
      <button type="button" disabled={pending || disabled} onClick={() => { setOpen(false); onManage() }}><Settings size={15} />管理模型</button>
    </section>}
  </div>
}
