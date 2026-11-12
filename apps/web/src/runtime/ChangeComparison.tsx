import { ArrowRight } from 'lucide-react'
import type { ChangePreview } from './workspace-chat'
import './change-comparison.css'

const labels: Record<string, string> = { name: '名称', term_name: '学期', start_date: '开始日期', end_date: '结束日期',
  title: '标题', due_at: '截止时间', status: '状态', student: '学生', source: '来源', body: '正文', format: '格式',
  subject: '科目', maximum_score: '满分', score: '成绩', reason: '更正原因', evidence: '跟进记录', fact_text: '事实', occurred_at: '发生时间' }
const statuses: Record<string, string> = { open: '未开始', 'not-started': '未开始', 'in-progress': '进行中', waiting: '等待别人',
  done: '已完成', cancelled: '已取消', scored: '已录入', absent: '缺考', exempt: '免考', 'not-recorded': '未录入' }
function display(field: string, value: string | null) {
  if (value === null || value === '') return '—'
  if (field === 'status') return statuses[value] || value
  if (field === 'format') return value === 'markdown' ? 'Markdown' : '纯文本'
  if (field === 'due_at' || field === 'occurred_at') return new Date(value).toLocaleString('zh-CN', { hour12: false })
  return value
}
function Board({ board, other }: { board: NonNullable<ChangePreview['after_seats']>; other: ChangePreview['before_seats'] }) {
  return <div className="change-seat-scroll"><div className="change-seats" role="table" aria-label="座位图" style={{ gridTemplateColumns: `repeat(${board.columns}, minmax(64px, 1fr))` }}>
    {Array.from({ length: board.rows }, (_, index) => <div role="row" className="change-seat-row" key={index}>
    {board.cells.filter(cell => cell.row === index + 1).map(cell => {
      const prior = other?.cells.find(value => value.row === cell.row && value.column === cell.column)
      const changed = !prior || prior.student_id !== cell.student_id || prior.student !== cell.student
      return <div role="cell" key={`${cell.row}-${cell.column}`} className={changed ? 'change-seat changed' : 'change-seat'}
        aria-label={`${cell.row}排${cell.column}座：${cell.student || '空座'}${changed ? '（有变动）' : ''}`}>
        <small>{cell.row}-{cell.column}</small><span>{cell.student || '空座'}</span>{changed && <span className="sr-only">有变动</span>}
      </div>
    })}</div>)}
  </div></div>
}
export function ChangeComparison({ preview, saved = false }: { preview: ChangePreview; saved?: boolean }) {
  return <section className="change-comparison" aria-label="变更前后对比">
    <div className="change-side" aria-label="修改前"><h3>修改前</h3>
      {preview.kind === 'create' || preview.kind === 'seating' && !preview.before_seats ? <p className="change-empty">尚未创建</p>
        : preview.before_seats ? <Board board={preview.before_seats} other={preview.after_seats} />
          : <dl>{preview.fields.map(field => <div key={field.field} className={field.before !== field.after ? 'changed' : ''}>
            <dt>{labels[field.field]}</dt><dd>{display(field.field, field.before)}</dd>
          </div>)}</dl>}
    </div>
    <ArrowRight className="change-arrow" size={20} aria-label="变更为" />
    <div className="change-side" aria-label={saved ? '已保存的结果' : '待确认的结果'}><h3>{saved ? '已保存' : '调整后'}</h3>
      {preview.after_seats ? <Board board={preview.after_seats} other={preview.before_seats} />
        : <dl>{preview.fields.map(field => <div key={field.field} className={field.before !== field.after ? 'changed' : ''}>
          <dt>{labels[field.field]}</dt><dd>{display(field.field, field.after)}</dd>
        </div>)}</dl>}
    </div>
  </section>
}
