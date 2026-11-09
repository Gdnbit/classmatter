import { useEffect, useRef, useState } from 'react'
import type { Classroom, Session, Student } from './api'
import { classroomClient, type ClassroomCommand, type ClassroomPreview, type Exam, type ExamResults, type ScoreStatus, type Seating } from './classroom-work'
import { R1Dialog } from './R1Dialog'

type Props = { session: Session; classroom: Classroom; students: Student[]; canWrite: boolean; revision: number; refreshSignal: unknown; previewOpen: boolean;
  onPreview: (value: ClassroomPreview, names: Record<string, string>) => void; onError: (error: unknown) => void;
  onDirty: (dirty: boolean) => void; onAsk: (text: string) => void }
const statusNames: Record<ScoreStatus, string> = { scored: '已录入', absent: '缺考', exempt: '免考', 'not-recorded': '未录入' }

export function GradesWorkspace(p: Props) {
  const [exams, setExams] = useState<Exam[]>([]), [selected, setSelected] = useState(''), [results, setResults] = useState<ExamResults | null>(null)
  const [loading, setLoading] = useState(true), [truncated, setTruncated] = useState(false), [search, setSearch] = useState('')
  const [failed, setFailed] = useState(false)
  const [draft, setDraft] = useState<{ student: Student; version: number; score: string; status: ScoreStatus; reason: string } | null>(null)
  const [previewing, setPreviewing] = useState(false), generation = useRef(0), latest = useRef(p); latest.current = p
  const api = classroomClient(p.session, p.classroom)
  useEffect(() => { setDraft(null) }, [p.revision])
  useEffect(() => { p.onDirty(!!draft); return () => p.onDirty(false) }, [!!draft, p.onDirty])
  useEffect(() => {
    if (draft) return
    const controller = new AbortController(), current = ++generation.current
    setLoading(true); setFailed(false); setResults(null)
    void (async () => {
      const listing = await api.exams(controller.signal)
      if (current !== generation.current) return
      setExams(listing.exams); setTruncated(listing.truncated)
      const id = listing.exams.some(exam => exam.exam_id === selected) ? selected : listing.exams[0]?.exam_id || ''
      if (id !== selected) { setSelected(id); return }
      if (id) {
        const value = await api.results(id, controller.signal)
        if (current === generation.current) setResults(value)
      }
    })().catch(error => { if (!controller.signal.aborted && current === generation.current) { setFailed(true); latest.current.onError(error) } })
      .finally(() => { if (!controller.signal.aborted && current === generation.current) setLoading(false) })
    return () => { generation.current++; controller.abort() }
  }, [selected, p.revision, p.refreshSignal, !!draft, p.session.csrf_token, p.classroom.class_id, p.classroom.term_id])
  async function preview() {
    if (!draft || !results || !p.canWrite || loading || previewing) return
    const current = generation.current
    setPreviewing(true)
    try {
      const value = await api.preview({ command: 'score.record', class_id: p.classroom.class_id, term_id: p.classroom.term_id,
        exam_id: results.exam_id, student_id: draft.student.student_id, expected_version: draft.version,
        status: draft.status, score: draft.status === 'scored' ? draft.score : null, reason: draft.reason })
      if (current === generation.current) p.onPreview(value, { [results.exam_id]: `${results.title} · ${results.subject}` })
    } catch (error) { if (current === generation.current) p.onError(error) }
    finally { if (current === generation.current) setPreviewing(false) }
  }
  return <section className="classroom-grades" aria-label="成绩表格">
    <div className="surface-title"><div><h1>成绩</h1>{results && <p>{results.title} · {results.subject} · 满分 {results.maximum_score}</p>}</div></div>
    <div className="r1-toolbar">
      <select aria-label="选择考试" value={selected} disabled={!!draft || previewing} onChange={event => setSelected(event.target.value)}>
        {!exams.length && <option value="">暂无考试</option>}{exams.map(exam => <option key={exam.exam_id} value={exam.exam_id}>{exam.title} · {exam.subject}</option>)}
      </select>
      <input aria-label="搜索成绩中的学生" placeholder="搜索学生" value={search} onChange={event => setSearch(event.target.value)} />
      <button onClick={() => p.onAsk('帮我建立一次考试。')} disabled={!!draft}>新建考试</button>
    </div>
    {loading ? <p role="status">正在读取成绩…</p> : failed ? <p>暂时无法读取成绩，请刷新重试。</p> : !exams.length ? <p>尚无考试。</p> : results && <>
      <p>{results.scored_count} 人已录入 · 平均分 {results.average ?? '暂无'}</p>
      <div className="sheet-grid" role="table" aria-label="学生成绩">
        <div className="sheet-row" role="row" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>{['姓名', '成绩', '状态', '操作'].map(label => <span role="columnheader" key={label}>{label}</span>)}</div>
        {p.students.filter(student => !search || student.name.includes(search)).map(student => {
          const result = results.results.find(row => row.student_id === student.student_id)
          return <div className="sheet-row" role="row" key={student.student_id} style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr' }}>
            <span role="cell">{student.name}</span><span role="cell">{result?.score ?? '—'}</span>
            <span role="cell">{statusNames[result?.status ?? 'not-recorded']}</span>
            <button disabled={!p.canWrite || !!draft || previewing || student.status !== 'active'} aria-label={`编辑${student.name}的成绩`}
              onClick={() => setDraft({ student, version: result?.version ?? 0, score: result?.score ?? '', status: result?.status ?? 'scored', reason: '' })}>编辑</button>
          </div>
        })}
      </div>
    </>}
    {truncated && <p>仅显示最近 50 场考试。</p>}
    {draft && !p.previewOpen && <R1Dialog titleId="score-edit-title" busy={previewing} onDismiss={() => setDraft(null)}><h2 id="score-edit-title">{draft.student.name} · 成绩</h2>
      <label>状态<select aria-label="成绩状态" value={draft.status} disabled={previewing} onChange={event => setDraft({ ...draft, status: event.target.value as ScoreStatus })}>
        {Object.entries(statusNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
      {draft.status === 'scored' && <label>分数<input aria-label="分数" inputMode="decimal" value={draft.score} disabled={previewing} onChange={event => setDraft({ ...draft, score: event.target.value })} /></label>}
      {draft.version > 0 && <label>更正原因<input aria-label="成绩更正原因" value={draft.reason} disabled={previewing} maxLength={500} onChange={event => setDraft({ ...draft, reason: event.target.value })} /></label>}
      <button disabled={previewing || !p.canWrite || draft.status === 'scored' && !draft.score || draft.version > 0 && !draft.reason.trim()} onClick={() => void preview()}>预览修改</button>
      <button disabled={previewing} onClick={() => setDraft(null)}>取消</button>
    </R1Dialog>}
  </section>
}

export function SeatingWorkspace(p: Props) {
  const [layout, setLayout] = useState<Seating | null>(null), [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [selected, setSelected] = useState<{row: number; column: number} | null>(null), [assigning, setAssigning] = useState(''), [previewing, setPreviewing] = useState(false)
  const drag = useRef<{row: number; column: number; version: number} | null>(null), generation = useRef(0), latest = useRef(p); latest.current = p
  const api = classroomClient(p.session, p.classroom), names = Object.fromEntries(p.students.map(student => [student.student_id, student.name]))
  useEffect(() => {
    const controller = new AbortController(), current = ++generation.current
    setLoading(true); setFailed(false); setSelected(null); drag.current = null
    void api.seating(controller.signal).then(value => { if (current === generation.current) setLayout(value.layout) })
      .catch(error => { if (!controller.signal.aborted && current === generation.current) { setFailed(true); latest.current.onError(error) } })
      .finally(() => { if (!controller.signal.aborted && current === generation.current) setLoading(false) })
    return () => { generation.current++; controller.abort() }
  }, [p.revision, p.refreshSignal, p.session.csrf_token, p.classroom.class_id, p.classroom.term_id])
  async function preview(command: ClassroomCommand) {
    if (!p.canWrite || loading || failed || previewing) return
    const current = generation.current
    setPreviewing(true)
    try { const value = await api.preview(command); if (current === generation.current) p.onPreview(value, names) }
    catch (error) { if (current === generation.current) p.onError(error) }
    finally { if (current === generation.current) setPreviewing(false) }
  }
  function swap(from: {row: number; column: number}, to: {row: number; column: number}) {
    if (!layout || from.row === to.row && from.column === to.column) { setSelected(null); return }
    void preview({ command: 'seat.swap', class_id: p.classroom.class_id, term_id: p.classroom.term_id, layout_id: layout.layout_id,
      expected_version: layout.version, first_row: from.row, first_column: from.column, second_row: to.row, second_column: to.column })
  }
  return <section className="seat-workspace" aria-label="座位图">
    <div className="seat-header"><h1>座位</h1></div>
    {loading ? <p role="status">正在读取座位…</p> : failed ? <p>暂时无法读取座位，请刷新重试。</p> : !layout ? <><p>尚无座位表。</p><button onClick={() => p.onAsk('帮我建立教室座位表。')}>建立座位表</button></> : <>
      <div className="r1-toolbar"><select aria-label="安排座位的学生" value={assigning} onChange={event => { setAssigning(event.target.value); setSelected(null) }} disabled={previewing}>
        <option value="">选择两处座位交换</option>{p.students.filter(student => student.status === 'active').map(student => <option key={student.student_id} value={student.student_id}>{student.name}</option>)}</select>
        {selected && <button onClick={() => setSelected(null)}>取消选择</button>}
      </div>
      <div className="seat-grid">{Array.from({ length: layout.rows }, (_, r) => <div className="seat-row" key={r} style={{ gridTemplateColumns: `repeat(${layout.columns}, minmax(68px, 1fr))` }}>
        {layout.seats.filter(cell => cell.row_index === r + 1).map(cell => {
          const position = { row: cell.row_index, column: cell.column_index }, name = cell.student_id ? names[cell.student_id] || '未在当前名单中' : '空座'
          return <button key={cell.column_index} className={`seat${selected?.row === position.row && selected.column === position.column ? ' selected' : ''}`}
            disabled={!p.canWrite || previewing} aria-label={`${position.row}排${position.column}座 ${name}`} draggable={!!cell.student_id && p.canWrite && !previewing}
            onDragStart={event => { drag.current = { ...position, version: layout.version }; event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', 'seat') }}
            onDragEnd={() => { drag.current = null }} onDragOver={event => { if (drag.current && p.canWrite) event.preventDefault() }}
            onDrop={event => { event.preventDefault(); const source = drag.current; drag.current = null; if (source?.version === layout.version) swap(source, position) }}
            onClick={() => { if (assigning) { void preview({ command: 'seat.assign', class_id: p.classroom.class_id, term_id: p.classroom.term_id, layout_id: layout.layout_id, expected_version: layout.version, student_id: assigning, ...position }); return }
              if (selected) swap(selected, position); else setSelected(position) }}>
            <small>{position.row}排{position.column}座</small><strong>{name}</strong>
          </button>
        })}
      </div>)}</div>
    </>}
  </section>
}
