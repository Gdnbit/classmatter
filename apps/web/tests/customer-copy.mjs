import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { previewFields, userMessage } from '../src/runtime/user-facing.ts';

test('confirmation shows the target name and actual change, never command metadata', () => {
  const payload = { command: 'task.update', task_id: 'internal-task', student_id: 'internal-student', expected_version: 7, status: 'waiting', evidence: '等待家长回复', due_at: null, change_due_date: false };
  const original = structuredClone(payload);
  const view = previewFields(payload, { 'internal-task': '收集回执', 'internal-student': '示例学生' });
  assert(view.some(([label, value]) => label === '跟进' && value === '收集回执'));
  assert(view.some(([label, value]) => label === '学生' && value === '示例学生'));
  assert(view.some(([label, value]) => label === '状态' && value === '等待别人'));
  assert(view.some(([label, value]) => label === '结果说明' && value === '等待家长回复'));
  assert(!JSON.stringify(view).match(/internal-|expected_version|task.update/));
  assert(!view.some(([label]) => label === '截止时间')); // A state-only change never claims to clear the deadline.
  assert.deepEqual(payload, original);
  assert(previewFields({ ...payload, change_due_date: true }).some(([label, value]) => label === '截止时间' && value === '不设置截止时间'));
});

test('before and after values remain reviewable without exposing internal versions', () => {
  const view = previewFields({ command: 'term.update', expected_version: 3, previous_name: '上学期', name: '新学期', previous_start_date: '2026-09-01', start_date: '2026-09-02' });
  assert(view.some(([label, value]) => label === '原名称' && value === '上学期'));
  assert(view.some(([label, value]) => label === '开始日期' && value === '2026-09-02'));
  assert(!view.some(([label]) => label.includes('版本')));
});

test('errors give a next action without leaking implementation checks or claiming success', () => {
  assert.equal(userMessage('Failed to fetch'), '连接中断，请稍后重试。');
  const message = userMessage('服务响应契约或回执绑定校验不匹配');
  assert.match(message, /核对操作结果/);
  assert(!/契约|回执|已保存|已回滚/.test(message));
  assert.equal(userMessage('内容已更新，请刷新后重新确认。'), '内容已更新，请刷新后重新确认。');
});

test('teacher-facing pages do not restore removed development explanations', async () => {
  for (const file of ['R1App.tsx','StudentDirectory.tsx','CommandPreview.tsx','DocumentsWorkspace.tsx','WorkSummary.tsx','ModelConfiguration.tsx','AttributionLabel.tsx','DurableExit.tsx']) {
    const source = await readFile(new URL(`../src/runtime/${file}`, import.meta.url), 'utf8');
    assert(!/同一数据世界|共享实体 · 多视图|内部 ID|可替换 AI 能力|完整性摘要|当前 owner|作者标识：|本切片|风险 X/.test(source), file);
  }
});

test('conversation does not restore routine maintenance controls or slogans', async () => {
  const chat = await readFile(new URL('../src/runtime/WorkspaceChat.tsx', import.meta.url), 'utf8');
  assert(!/刷新对话|归档对话|清除聊天正文|这项操作尚未保存|核对文档正文（/.test(chat));
  const shell = await readFile(new URL('../src/runtime/R1App.tsx', import.meta.url), 'utf8');
  assert(!/少记、少追、少重复|CLASSMATTER · 对话/.test(shell));
  assert(chat.includes('aria-label="输入消息"'));
  assert(chat.includes('aria-label="操作权限"'));
});
