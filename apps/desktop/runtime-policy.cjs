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
function officeDownload(origin,value,mime,size) {
  if(!allowed(origin,value)||!Number.isSafeInteger(size)||size<=0||size>4*1024*1024)return false;
  const url=new URL(value),id='[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}';
  const match=url.pathname.match(new RegExp('^/api/workspaces/'+id+'/classes/'+id+'/terms/'+id+'/documents/'+id+'/exports/([1-9][0-9]{0,9})/(docx|pptx)$'));
  if(url.search||url.hash||!match||Number(match[1])>2147483647)return false;
  return mime===({docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation'}[match[2]]);
}
function clipboardWrite(origin,permission,details) {
  return permission==='clipboard-sanitized-write' && details?.isMainFrame===true && allowed(origin,details.requestingUrl);
}
function microphoneRequest(origin,permission,details) {
  return permission==='media' && details?.isMainFrame===true && allowed(origin,details.requestingUrl)
    && Array.isArray(details.mediaTypes) && details.mediaTypes.length===1 && details.mediaTypes[0]==='audio';
}
function microphoneCheck(origin,permission,details) {
  return permission==='media' && details?.isMainFrame===true && allowed(origin,details.requestingUrl) && details.mediaType==='audio';
}
module.exports={allowed,CSP,exitDownload,officeDownload,clipboardWrite,microphoneRequest,microphoneCheck};
