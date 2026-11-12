import { useEffect, useRef, useState } from 'react'
import { ApiError, type Session } from './api'
import { importCapture } from './composer-capture'
import type { WorkspaceChatController } from './useWorkspaceChat'

export function useComposerInput(state: WorkspaceChatController, session: Session, onError: (error: unknown) => void) {
  const current = useRef(state); current.current = state
  const serial = useRef(0), active = useRef(false), controller = useRef<AbortController | null>(null)
  const recorder = useRef<{ capture: MediaRecorder; key: string; preserve: boolean; transcribe: boolean } | null>(null), stream = useRef<MediaStream | null>(null)
  const openingKey = useRef<string | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null), limit = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [busy, setBusy] = useState(false), [recording, setRecording] = useState(false), [seconds, setSeconds] = useState(0)
  const [status, setStatus] = useState(''), [error, setError] = useState('')
  function release() {
    if (timer.current) clearInterval(timer.current)
    if (limit.current) clearTimeout(limit.current)
    timer.current = null; limit.current = null
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null
  }
  function detach(preserve = true) {
    serial.current++; controller.current?.abort(); controller.current = null
    const owned = recorder.current
    if (owned) {
      owned.preserve = preserve; owned.transcribe = false
      if (!preserve) current.current.markRecording(owned.key, false)
      if (owned.capture.state === 'recording') owned.capture.stop()
    } else if (openingKey.current) current.current.markRecording(openingKey.current, false)
    openingKey.current = null
    recorder.current = null; release(); active.current = false
  }
  function cancel() {
    if (recorder.current && !window.confirm('丢弃这段录音？未转成文字的内容将无法恢复。')) return
    detach(false); setBusy(false); setRecording(false); setStatus(''); setError('')
  }
  useEffect(() => {
    setBusy(false); setRecording(false); setSeconds(0); setStatus(''); setError('')
    return () => detach(true)
  }, [state.draftKey])
  async function files(values: File[], dictated = false) {
    if (active.current || !values.length) return
    if (values.length > 3) { setError('每次最多添加3个文件。'); return }
    const key = current.current.inputSnapshot().key, version = ++serial.current
    const abort = new AbortController(); controller.current = abort
    active.current = true; setBusy(true); setError('')
    try {
      for (const file of values) {
        if (file.name.length > 120) throw new Error('文件名过长，请缩短后重试。')
        const snapshot = current.current.inputSnapshot()
        if (snapshot.key !== key) return
        const prefix = dictated ? (snapshot.text && !/\s$/.test(snapshot.text) ? '\n' : '') : `${snapshot.text ? '\n\n' : ''}《${file.name}》\n`
        const capacity = 2000 - snapshot.text.length - prefix.length
        if (capacity <= 0) throw new Error('本条消息已满，请先发送或精简文字。')
        setStatus(dictated ? '正在识别语音…' : `正在读取 ${file.name}…`)
        const text = await importCapture(session, file, capacity, abort.signal)
        if (version !== serial.current || abort.signal.aborted) return
        const latestText = current.current.inputSnapshot().text
        const finalPrefix = dictated ? (latestText && !/\s$/.test(latestText) ? '\n' : '') : `${latestText ? '\n\n' : ''}《${file.name}》\n`
        if (!current.current.appendInput(finalPrefix + text, key)) throw new Error('本条消息放不下更多文字，请先发送或精简。')
        if (dictated) current.current.clearRecording(key, file)
      }
      if (version === serial.current) setStatus('文字已加入，可直接修改。')
    } catch (failure) {
      if (version === serial.current && !abort.signal.aborted) {
        setStatus(''); setError(failure instanceof Error ? failure.message : '识别未完成，请重试。')
        if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) onError(failure)
      }
    } finally {
      if (version === serial.current) { active.current = false; setBusy(false); controller.current = null }
    }
  }
  function finishRecording() {
    if (recorder.current?.capture.state !== 'recording') return
    recorder.current.transcribe = true
    setRecording(false); setBusy(true); setStatus('正在识别语音…'); recorder.current.capture.stop()
  }
  async function microphone() {
    if (recording) { finishRecording(); return }
    if (active.current) return
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported('audio/webm')) {
      setError('此浏览器暂不支持录音，可添加音频文件。'); return
    }
    const version = ++serial.current, key = current.current.inputSnapshot().key
    if (!current.current.markRecording(key, true)) { setError('请先处理已有录音，再开始录音。'); return }
    openingKey.current = key
    active.current = true; setBusy(true); setError(''); setStatus('正在打开麦克风…')
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 }, video: false })
      if (version !== serial.current || current.current.inputSnapshot().key !== key) { media.getTracks().forEach(track => track.stop()); return }
      stream.current = media
      const chunks: BlobPart[] = [], capture = new MediaRecorder(media, { mimeType: 'audio/webm', audioBitsPerSecond: 32000 })
      const owned = { capture, key, preserve: true, transcribe: false }
      recorder.current = owned; openingKey.current = null
      capture.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      capture.onstop = () => {
        media.getTracks().forEach(track => track.stop())
        if (!owned.preserve) return
        const audio = new File(chunks, '录音.webm', { type: 'audio/webm' })
        const retained = current.current.retainRecording(audio, key)
        if (!retained) current.current.markRecording(key, false)
        if (version !== serial.current || current.current.inputSnapshot().key !== key) return
        release(); recorder.current = null; active.current = false; setRecording(false)
        if (!retained) { setBusy(false); setStatus(''); setError(audio.size ? '录音较大，请缩短后重试。' : '没有录到声音，请重新录音。'); return }
        if (owned.transcribe) void files([audio], true)
        else setBusy(false)
      }
      capture.onerror = () => { if (version === serial.current) { detach(true); setBusy(false); setRecording(false); setError('录音中断，可重试识别。') } }
      capture.start(1000); setBusy(false); setRecording(true); setSeconds(0); setStatus('')
      timer.current = setInterval(() => setSeconds(value => value + 1), 1000)
      limit.current = setTimeout(finishRecording, 180000)
    } catch (failure) {
      if (version === serial.current) {
        release(); openingKey.current = null; current.current.markRecording(key, false); active.current = false; setBusy(false); setStatus('')
        setError(failure instanceof DOMException && failure.name === 'NotAllowedError' ? '未允许使用麦克风，请允许后重试。' : '麦克风不可用，请检查设备后重试。')
      }
    }
  }
  function discardRecording() {
    const file = current.current.recordingFile
    if (file && window.confirm('丢弃这段录音？未转成文字的内容将无法恢复。')) {
      current.current.clearRecording(current.current.inputSnapshot().key, file); setError(''); setStatus('')
    }
  }
  return { busy, recording, seconds, status, error, files, microphone, cancel, discardRecording,
    retryRecording: () => { const file = current.current.recordingFile; if (file) void files([file], true) },
    clearNotice: () => { setStatus(''); setError('') } }
}
