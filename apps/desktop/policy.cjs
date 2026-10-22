const path = require('node:path');
const fs = require('node:fs/promises');

const ORIGIN = 'classmatter://app';
const CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'none'; media-src blob:; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'";
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.woff2': 'font/woff2', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };
// Existing Demo routes only: never turn arbitrary missing paths into HTML.
const ROUTE = /^\/(?:|students(?:\/[A-Za-z0-9_-]+)?|dashboard|work|data(?:\/(?:spreadsheets|documents)\/[A-Za-z0-9_-]+)?|inbox|automation|knowledge|reports|settings(?:\/user)?|spaces\/[A-Za-z0-9_-]+)$/;

function localURL(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'classmatter:' && url.hostname === 'app' && !url.port && !url.username && !url.password;
  } catch { return false; }
}

function resolveResource(value, method = 'GET') {
  if (!localURL(value) || !['GET', 'HEAD'].includes(method)) return null;
  let pathname;
  try { pathname = decodeURIComponent(new URL(value).pathname); } catch { return null; }
  if (pathname.includes('\\') || pathname.includes('\0') || pathname.split('/').some(p => p === '.' || p === '..')) return null;
  if (ROUTE.test(pathname)) return { relative: 'index.html', type: TYPES['.html'] };
  // Only Vite's generated flat assets; no maps, arbitrary files or API paths.
  if (!/^\/assets\/[A-Za-z0-9_-]+\.(?:js|css|woff2|png|svg|ico)$/.test(pathname)) return null;
  return { relative: pathname.slice(1), type: TYPES[path.extname(pathname)] };
}

async function serveResource(root, request) {
  const resource = resolveResource(request.url, request.method);
  const headers = { 'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' };
  if (!resource) return new Response(null, { status: 404, headers });
  try {
    const base = await fs.realpath(root);
    const file = await fs.realpath(path.join(base, resource.relative));
    const relative = path.relative(base, file);
    if (relative.startsWith('..') || path.isAbsolute(relative)) return new Response(null, { status: 403, headers });
    const bytes = await fs.readFile(file);
    return new Response(request.method === 'HEAD' ? null : bytes, { headers: { ...headers, 'Content-Type': resource.type } });
  } catch { return new Response(null, { status: 404, headers }); }
}

module.exports = { ORIGIN, CSP, localURL, resolveResource, serveResource };
