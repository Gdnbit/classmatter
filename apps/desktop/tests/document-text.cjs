const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createRequire } = require('node:module');
let parser;

// Test oracle uses the installed Markdown AST, not the React renderer or a
// hand-written syntax stripper. Exact candidate/revision bytes are checked
// separately through the real HTTP contract and saved document APIs.
async function documentText(body, format) {
  if (format !== 'markdown') return body;
  if (!parser) parser = (async () => {
    const web = createRequire(path.resolve(__dirname, '../../web/package.json'));
    const dependencies = createRequire(web.resolve('react-markdown'));
    const [{ unified }, { default: parse }, { default: gfm }, { default: math }, { default: rehype }, { defaultUrlTransform }] = await Promise.all([
      import(pathToFileURL(dependencies.resolve('unified')).href),
      import(pathToFileURL(dependencies.resolve('remark-parse')).href),
      import(pathToFileURL(web.resolve('remark-gfm')).href),
      import(pathToFileURL(web.resolve('remark-math')).href),
      import(pathToFileURL(dependencies.resolve('remark-rehype')).href),
      import(pathToFileURL(web.resolve('react-markdown')).href),
    ]);
    // Preserve raw HTML as inert AST text for comparison. Never insert this
    // tree into a DOM or execute it; production Markdown escapes raw HTML.
    return { processor: unified().use(parse).use(gfm).use(math).use(rehype, { allowDangerousHtml: true }), url: defaultUrlTransform };
  })();
  const { processor, url } = await parser;
  const tree = processor.runSync(processor.parse(body));
  function text(node) {
    if (node.type === 'element' && node.tagName === 'img') return node.properties.alt || '图片';
    const value = typeof node.value === 'string' ? node.value : (node.children || []).map(text).join('');
    const href = node.type === 'element' && node.tagName === 'a' && url(node.properties.href || '');
    return href ? value + '（' + href + '）' : value;
  }
  // Block separation and soft line breaks are layout, not lost business text.
  return text(tree).replace(/\s+/g, '');
}
async function documentFields(locator) {
  return locator.evaluateAll(nodes => Object.fromEntries(nodes.map(node => {
    const content = node.querySelector('dd').cloneNode(true);
    // Compare each actual rendered formula's source once, without its duplicate
    // accessible/visual trees. Fraction rendering itself has separate DOM tests.
    for (const math of content.querySelectorAll('.katex')) {
      const source = math.querySelector('annotation[encoding="application/x-tex"]');
      if (source) math.replaceWith(source.textContent);
    }
    return [node.querySelector('dt').textContent, content.textContent];
  })));
}
module.exports = { documentText, documentFields };
