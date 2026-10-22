import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createSeatPlan, projectSeatPlan, validateSeats } from '../src/demo/seat-plan.ts'

const students = Array.from({length:36}, (_,i) => ({id:String(99001+i),name:`合成学生${String(i+1).padStart(2,'0')}`,seat:`${Math.floor(i/6)+1}排${i%6+1}座`,status:'在读',dorm:'合成寝室',group:'合成组'}))
test('exact requested identities and actual source seats determine preview', () => {
  const plan = createSeatPlan(students, '交换合成学生01和合成学生02的座位，先给我预览')
  assert.deepEqual(plan.changes.map(c => c.studentId), ['99001','99002'])
  assert.deepEqual(plan.changes.map(c => [c.before,c.after]), [['1排1座','1排2座'],['1排2座','1排1座']])
  const next = projectSeatPlan(students,plan)
  assert.equal(next[0].seat,'1排2座')
  assert.equal(students[0].seat,'1排1座')
  assert.equal(next[4].seat,students[4].seat)
})
test('all 630 distinct student pairs preserve identity and one-to-one seats', () => {
  for(let a=0;a<36;a++)for(let b=a+1;b<36;b++){
    const plan=createSeatPlan(students,`互换 ${students[a].id} 和 ${students[b].id} 的座位`)
    const next=projectSeatPlan(students,plan)
    assert.deepEqual(validateSeats(next),[])
    assert.equal(next.length,36)
    assert.equal(next[a].seat,students[b].seat)
    assert.equal(next[b].seat,students[a].seat)
  }
})
test('ambiguous, unknown, duplicate, read-only, conditional and negated requests never fallback', () => {
  for(const request of ['换座位','交换合成学生01的座位','交换合成学生01和合成学生01的座位','交换合成学生01和合成学生99的座位','看看合成学生01和合成学生02的座位','不要交换合成学生01和合成学生02的座位','如果交换合成学生01和合成学生02的座位','交换合成学生010和合成学生02的座位','不允许交换合成学生01和合成学生02的座位','交换合成学生01和合成学生02的座位，并安排张三靠窗']) assert.throws(()=>createSeatPlan(students,request))
})
test('stale snapshots and malformed plans fail closed', () => {
  const plan=createSeatPlan(students,'交换合成学生01和合成学生02的座位')
  const next=projectSeatPlan(students,plan)
  assert.throws(()=>projectSeatPlan(next,plan),/已变化/)
  assert.throws(()=>projectSeatPlan(students,{changes:[plan.changes[0],plan.changes[0]]}))
  assert.throws(()=>projectSeatPlan(students,{changes:plan.changes.map(c=>({...c,after:'9排9座'}))}))
  assert.throws(()=>projectSeatPlan(students,{changes:plan.changes.map(c=>({...c,name:'不存在'}))}))
})
test('duplicate identity, invalid coordinate and collision in source data block preview', () => {
  for(const patch of [{id:'99002'},{seat:'1排2座'},{seat:'9排9座'}]){
    const invalid=students.map((s,i)=>i===0?{...s,...patch}:s)
    assert.ok(validateSeats(invalid).length)
    assert.throws(()=>createSeatPlan(invalid,'交换合成学生01和合成学生02的座位'))
  }
})
