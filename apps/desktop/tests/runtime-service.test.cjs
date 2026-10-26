const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { createHmac } = require('node:crypto');
const net = require('node:net');
const path = require('node:path');
const { OwnedService, serviceURL, validProof } = require('../runtime-service.cjs');
const { allowed, CSP, exitDownload } = require('../runtime-policy.cjs');

async function freePort() {
  const server = net.createServer();
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const port=server.address().port;
  await new Promise(resolve=>server.close(resolve));
  return port;
}
async function fixture(mode='ready') {
  const port=await freePort();
  let process;
  const service=new OwnedService({origin:`http://127.0.0.1:${port}`,timeout:1500,spawnService:key=>{
    process=spawn(global.process.execPath,[path.join(__dirname,'service-fixture.cjs'),String(port),mode],{env:{...global.process.env,CLASSMATTER_DESKTOP_PROCESS_KEY:key},windowsHide:true,stdio:'ignore'});
    return process;
  }});
  return {service,port,child:()=>process};
}
test('runtime accepts only explicit loopback HTTP origins without user data',()=>{
  assert.ok(serviceURL('http://127.0.0.1:8000'));
  for(const url of ['http://localhost:8000','https://127.0.0.1:8000','http://0.0.0.0:8000','http://127.0.0.1:80','http://user@127.0.0.1:8000','http://127.0.0.1:8000/?x=1','http://127.0.0.1:8000/api']) assert.equal(serviceURL(url),false,url);
});
test('runtime renderer stays on the verified origin; same-origin CSP does not grant shell or remote access',()=>{
  const origin='http://127.0.0.1:8000';
  assert.ok(allowed(origin,origin+'/api/identity/context'));
  for(const url of ['http://127.0.0.1:8443/','https://example.com/','file:///tmp/local','classmatter://app/','blob:http://127.0.0.1:8000/123','http://user@127.0.0.1:8000/']) assert.equal(allowed(origin,url),false);
  assert.match(CSP,/connect-src 'self'/);assert.match(CSP,/frame-src 'none'/);assert.doesNotMatch(CSP,/unsafe-eval/);
});
test('only bounded JSON core or D1 exit receipt downloads may open a user Save dialog',()=>{
  const origin='http://127.0.0.1:8000',id='12345678-1234-1234-1234-123456789012',url=origin+'/api/workspaces/'+id+'/exit/'+id+'/download';
  assert.ok(exitDownload(origin,url,'application/json',100));
  const d1=url.replace('/exit/','/conversation-d1/exit/');
  assert.ok(exitDownload(origin,d1,'application/json',100));
  for(const target of [d1+'?x=1',d1+'#x',d1.replace('/conversation-d1/','/conversation-d2/'),d1.replace('/download','/preview')])assert.equal(exitDownload(origin,target,'application/json',100),false);
  for(const [target,mime,size] of [[url+'?x=1','application/json',100],[url,'text/html',100],[url,'application/json',0],[url,'application/json',17*1024*1024],[origin+'/assets/index.js','application/json',100]])assert.equal(exitDownload(origin,target,mime,size),false);
});
test('proof is exact, keyed and challenge-bound, not merely a green health response',()=>{
  const key='12'.repeat(32),challenge='34'.repeat(32);
  const proof=createHmac('sha256',Buffer.from(key,'hex')).update('classmatter.desktop.v1:'+challenge).digest('hex');
  const reply={schema_version:'classmatter.desktop-proof.v1',mode:'synthetic-only',challenge,proof};
  assert.ok(validProof(reply,key,challenge));
  for(const change of [{mode:'real'},{proof:'ff'.repeat(32)},{challenge:'00'.repeat(32)},{extra:true}]) assert.equal(validProof({...reply,...change},key,challenge),false);
});
test('real owned TCP process starts, verifies ready and closes; no restart/replay',async()=>{
  const {service,child}=await fixture();
  try {
    assert.equal(await service.start(),service.origin);
    assert.equal(service.state,'ready');
    await assert.rejects(service.start(),/already_started/);
  } finally { await service.stop(); }
  assert.ok(child().exitCode!==null || child().signalCode!==null);
  assert.equal(service.state,'stopped');
  await service.stop();
});
test('unexpected child death notifies the host without respawning or replaying',async()=>{
  const {service,child}=await fixture();let notified=0;
  service.onUnexpectedExit=()=>{notified++;};
  try {
    await service.start();
    const exit=new Promise(resolve=>child().once('exit',resolve));child().kill();await exit;
    assert.equal(service.state,'failed');assert.equal(notified,1);
    await assert.rejects(service.start(),/already_started/);
  } finally {await service.stop();}
});
for(const mode of ['wrong','not-ready','oversize','exit']) test(`startup ${mode} fails closed and stops only its child`,async()=>{
  const {service,child}=await fixture(mode);
  await assert.rejects(service.start(),/Desktop service unavailable/);
  assert.equal(service.state,'stopped');
  assert.ok(child().exitCode!==null || child().signalCode!==null);
});
test('occupied port rejects attachment and does not terminate the existing listener',async()=>{
  const server=net.createServer(socket=>socket.destroy());
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const port=server.address().port;
  const service=new OwnedService({origin:`http://127.0.0.1:${port}`,timeout:600,spawnService:key=>spawn(process.execPath,[path.join(__dirname,'service-fixture.cjs'),String(port),'ready'],{env:{...process.env,CLASSMATTER_DESKTOP_PROCESS_KEY:key},windowsHide:true,stdio:'ignore'})});
  try { await assert.rejects(service.start()); assert.ok(server.listening); }
  finally { await service.stop(); await new Promise(resolve=>server.close(resolve)); }
});
