import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
const { DocumentBody } = await server.ssrLoadModule('/src/runtime/DocumentBody.tsx');
const { ChangeComparison } = await server.ssrLoadModule('/src/runtime/ChangeComparison.tsx');
const render = (body, format = 'markdown') => renderToStaticMarkup(createElement(DocumentBody, { body, format }));
test.after(() => server.close());

test('existing Markdown becomes readable headings, lists, tables and inert checkboxes', () => {
  const body = '# 班级小结\n\n- 已收齐**展示作品**\n- 下周继续\n\n| 事项 | 结果 |\n| --- | --- |\n| 核对 | 完成 |\n\n- [x] 已核对';
  const html = render(body);
  assert.match(html, /<h1>班级小结<\/h1>/);
  assert.match(html, /<li>已收齐<strong>展示作品<\/strong><\/li>/);
  assert.match(html, /<table>/); assert.match(html, /<td>完成<\/td>/);
  assert.match(html, /type="checkbox"/); assert.match(html, /disabled=""/);
  assert.equal(body.startsWith('# 班级小结'), true); // No mutation of the canonical source.
});

test('plain text retains punctuation, newlines and literal markup', () => {
  const body = '# 原文\n**不要改写**\n<script>原文字样</script>';
  const html = render(body, 'plain-text');
  assert.match(html, /# 原文\n\*\*不要改写\*\*/);
  assert.match(html, /&lt;script&gt;原文字样&lt;\/script&gt;/);
  assert(!html.includes('<h1>') && !html.includes('<script>'));
});

test('generated HTML and remote resources do not execute or load automatically', () => {
  const html = render('<script>throw new Error("not executed")</script>\n\n![作品](https://example.invalid/image.png)\n\n[来源](https://example.invalid/source)\n\n[坏链接](javascript:alert(1))');
  assert(!/<script|<img|<iframe|onerror=|href=|src=/.test(html));
  assert.match(html, /作品/); assert.match(html, /https:\/\/example.invalid\/source/);
  assert(!html.includes('javascript:'));
});

test('each historical comparison uses its own before/after format, without mutating the preview', () => {
  const preview = { kind: 'edit', candidate_hash: 'synthetic', before_seats: null, after_seats: null, fields: [
    { field: 'body', before: '# 原来的原文', after: '# 新的小结\n\n- 核对完成' },
    { field: 'format', before: 'plain-text', after: 'markdown' },
  ] };
  const original = structuredClone(preview);
  const html = renderToStaticMarkup(createElement(ChangeComparison, { preview, saved: true }));
  assert.match(html, /# 原来的原文/); assert(!html.includes('<h1>原来的原文</h1>'));
  assert.match(html, /<h1>新的小结<\/h1>/); assert.match(html, /<li>核对完成<\/li>/);
  assert.match(html, /普通文本/); assert.match(html, /排版文本/); assert(!html.includes('Markdown'));
  assert.match(html, /已保存的结果/); assert.deepEqual(preview, original);
});
