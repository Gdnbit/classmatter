const { serviceURL } = require('./runtime-service.cjs');
const CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'";
function allowed(origin, value) {
  if (!serviceURL(origin)) return false;
  try { const url=new URL(value); return url.protocol==='http:' && url.origin===new URL(origin).origin && !url.username && !url.password; }
  catch { return false; }
}
function exitDownload(origin,value,mime,size) {
  if(!allowed(origin,value) || mime!=='application/json' || !Number.isSafeInteger(size) || size<=0 || size>16*1024*1024)return false;
  const url=new URL(value),id='[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}';
  return !url.search && !url.hash && new RegExp('^/api/workspaces/'+id+'/(?:conversation-d1/)?exit/'+id+'/download$').test(url.pathname);
}
module.exports={allowed,CSP,exitDownload};
