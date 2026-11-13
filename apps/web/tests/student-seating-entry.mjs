import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { StudentViewSwitcher } = await server.ssrLoadModule('/src/shell/StudentPresentation.tsx');
test.after(() => server.close());
const render = props => renderToStaticMarkup(createElement(StudentViewSwitcher, { current: '清单', onSelect() {}, ...props }));
const tab = (html, label) => html.match(new RegExp(`<button[^>]*>${label}</button>`))[0];

test('ordinary connected scope retains unavailable seats and other future views', () => {
  const html = render({ connected: true });
  for (const name of ['清单', '表格']) assert(!tab(html, name).includes('disabled'));
  for (const name of ['座位', '宿舍', '小队', '画布']) assert(tab(html, name).includes('disabled'));
});

test('an admitted seating action opens only the existing seats entry; prototype tabs remain unchanged', () => {
  const html = render({ connected: true, onOpenSeating() {} });
  assert(!tab(html, '座位').includes('disabled')); assert(!tab(html, '座位').includes('暂不可用'));
  for (const name of ['宿舍', '小队', '画布']) assert(tab(html, name).includes('disabled'));
  const prototype = render({ connected: false });
  assert(!prototype.includes('disabled')); assert.equal((prototype.match(/role="tab"/g) || []).length, 6);
  assert.match(html, /aria-label="学生视图切换"/);
});
