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

test('teaching fractions and block equations render accessible math without rewriting the source', () => {
  const body = '# 认识分数\n\n每份是 $\\frac{1}{2}$。\n\n$$\n\\frac{1}{2} + \\frac{1}{4} = \\frac{3}{4}\n$$';
  const html = render(body);
  assert.match(html, /class="katex"/); assert.match(html, /class="katex-display"/);
  assert.match(html, /<math/); assert.match(html, /<mfrac>/);
  assert.match(html, /encoding="application\/x-tex"/);
  assert.equal(body.includes('$\\frac{1}{2}$'), true);
  const plain = render(body, 'plain-text');
  assert(!plain.includes('class="katex')); assert.match(plain, /\$\\frac\{1\}\{2\}\$/);
  const code = render('`$\\frac{1}{2}$`\n\n```text\n$\\frac{1}{2}$\n```');
  assert(!code.includes('class="katex')); assert.match(code, /<code>\$\\frac/);
});

test('invalid formulas and bounded recursive macros cannot break the remaining answer or leak across renders', () => {
  const html = render('$\\frac{1}{$\n\n后面的工作安排仍可阅读。\n\n$\\def\\loop{\\loop}\\loop$');
  assert.match(html, /后面的工作安排仍可阅读/); assert.match(html, /katex-error/);
  assert(!html.includes('title="ParseError'));
  render('$\\gdef\\saved{SYNTHETICMACRO}\\saved$');
  const next = render('$\\saved$');
  assert(!next.includes('SYNTHETICMACRO')); assert.match(next, /<mtext>\\saved<\/mtext>/);
});

test('formula rendering cannot introduce external resources or model-supplied HTML attributes', () => {
  const html = render('$\\includegraphics{https://example.invalid/a.png}$\n\n$\\href{https://example.invalid}{外链}$\n\n$\\htmlClass{synthetic-canary}{x}$\n\n$\\rule{9999em}{9999em}$');
  assert(!/<img|<a\b|href=|src=|class="synthetic-canary"/.test(html));
  assert(!/(?:style|width|height)="[^"]*9999em/.test(html)); assert.match(html, /<math/);
});
