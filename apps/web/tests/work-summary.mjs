import test from 'node:test'
import assert from 'node:assert/strict'
import { workSummary } from '../src/runtime/work-summary.ts'

const classroom = { class_id: 'c', term_id: 't', name: '合成班', term_name: '合成学期', version: 1 }
const record = { record_id: 'r', version: 1, student_id: 's', kind: 'ordinary_fact', occurred_at: '2026-10-01T00:00:00Z',
  recorded_at: '2026-10-01T00:00:00Z', fact_text: '合成旧事实', observation_text: '合成观察', source: '人工登记', revision_kind: 'original', revision_reason: '', related_record_id: null }
const activity = { as_of: '2026-10-27T00:00:00Z', records: [record], tasks: [{ task_id: 'q', version: 1,
  title: '合成待办', status: 'waiting', overdue: false, student_id: null, due_at: null, source_record_id: 'r', evidence: '' }] }
const students = [{ student_id: 's', name: '合成学生', version: 1, status: 'active' }]
test('summary deduplicates by highest revision before presentation, preserves observation boundary and citations', () => {
  const result = workSummary(classroom, { ...activity, records: [{ ...record, version: 2, fact_text: '合成更正事实' }, record] }, students)
  assert.equal(result.recordCount, 1)
  assert(result.text.includes('[record:r@2]'))
  assert(!result.text.includes('合成旧事实'))
  assert(result.text.includes('教师观察字段（不等于事实）：合成观察'))
  assert(result.text.includes('[task:q@1]'))
  assert(result.text.includes('不代表责任转移'))
  assert.equal(activity.records[0].version, 1)
})
test('complete source set, names, scope and content change invalidate basis; query time and overdue alone do not', () => {
  const baseline = workSummary(classroom, activity, students).basis
  assert.equal(workSummary(classroom, { ...activity, as_of: 'later', tasks: [{ ...activity.tasks[0], overdue: true }] }, students).basis, baseline)
  for (const changed of [{ ...activity, records: [] }, { ...activity, records: [...activity.records, { ...record, record_id: 'new' }] },
    { ...activity, tasks: [{ ...activity.tasks[0], status: 'done' }] }])
    assert.notEqual(workSummary(classroom, changed, students).basis, baseline)
  assert.notEqual(workSummary({ ...classroom, term_id: 'other' }, activity, students).basis, baseline)
  assert.notEqual(workSummary(classroom, activity, [{ ...students[0], name: '更正姓名' }]).basis, baseline)
})
test('empty is not completion and bounds reject instead of silent truncation', () => {
  assert(workSummary(classroom, { ...activity, records: [], tasks: [] }, []).text.includes('不能据此推断'))
  assert.throws(() => workSummary(classroom, { ...activity, records: Array.from({ length: 101 }, (_, i) => ({ ...record, record_id: String(i) })) }, []), /100项/)
  assert.throws(() => workSummary(classroom, { ...activity, records: [{ ...record, fact_text: 'a'.repeat(64001) }] }, []), /64000/)
})
test('imported renamed task retains original author and local modifier separately', () => {
  const attribution = { origin: 'source-import', created_by: 'source-author', last_modified_by: 'current-owner',
    content_authority: 'domain-data', source_workspace_id: 'source-workspace', source_owner_id: 'source-owner', source_version: 1 }
  const result = workSummary(classroom, { ...activity, tasks: [{ ...activity.tasks[0], version: 2, title: '本地更名', attribution }] }, students)
  assert(result.text.includes('来源作者：source-author · 最近修改者：current-owner'))
  assert(result.text.includes('原工作区：source-workspace'))
  assert(result.text.includes('[task:q@2] 本地更名'))
})
