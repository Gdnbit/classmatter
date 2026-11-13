const test = require('node:test');
const assert = require('node:assert/strict');
const { documentText } = require('./document-text.cjs');

test('native preview oracle retains Markdown business text without syntax and leaves plain text exact', async () => {
  const body = '# 小结\n\n- 核对**作品**\n- [x] 已完成\n\n| 学生 | 结果 |\n| --- | --- |\n| 甲 | 已核对 |\n\n[来源](https://example.invalid/source)\n\n![作品图](https://example.invalid/image)';
  assert.equal(await documentText(body, 'markdown'), '小结核对作品已完成学生结果甲已核对来源（https://example.invalid/source）作品图');
  assert.equal(await documentText(body, 'plain-text'), body);
  assert.equal(await documentText('事实：\\*原字样\\*，分数80→88.5。', 'markdown'), '事实：*原字样*，分数80→88.5。');
  assert.equal(await documentText('[来源][source]\n\n[source]: https://example.invalid/source\n\n[无效](javascript:alert(1))', 'markdown'), '来源（https://example.invalid/source）无效');
  assert.equal(await documentText('每份 $\\frac{1}{2}$。\n\n$$\nx+1=2\n$$', 'markdown'), '每份\\frac{1}{2}。x+1=2');
});
