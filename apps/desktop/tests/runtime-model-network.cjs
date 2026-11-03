// Real owned Electron/API/PG startup, synthetic key only; never calls a model.
const {_electron:electron}=require('playwright-core');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {electronArguments}=require('../model-network.cjs');
const desktop=path.resolve(__dirname,'..'),stage=path.join(desktop,'.build/runtime');
const fixture=process.env.CLASSMATTER_TEST_RUNTIME_ROOT;
if(!fixture||!path.isAbsolute(fixture))throw new Error('Owned synthetic fixture required');
const file=path.join(stage,'runtime-source.json'),original=fs.readFileSync(file);
const source=JSON.parse(original);source.runtimeRoot=fixture;
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const base='https://generativelanguage.googleapis.com/v1beta/openai/';
let app,phase='prepare';
async function launch(network){
  app=await electron.launch({executablePath:require('electron'),args:[stage,...electronArguments(network)],env});
  const page=await app.firstWindow();
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.getByRole('heading',{name:'今天想处理什么？',exact:true}).waitFor();
  return page;
}
async function inspect(page,save){
  return page.evaluate(async ({base,save})=>{
    const context=await(await fetch('/api/identity/session')).json(),root='/api/workspaces/'+context.subject.workspace_id;
    const config=root+'/agent/configuration',headers={'content-type':'application/json','x-class-os-csrf':context.csrf_token};
    const post=async(url,body)=>{const result=await fetch(url,{method:'POST',headers,body:JSON.stringify(body)});if(!result.ok)throw new Error('Synthetic controlled request failed '+result.status);return result.json();};
    if(save){
      const key='synthetic-desktop-provider-canary';
      const staged=await post(config+'/stage',{protocol:'chat-completions',model:'gemini-3.1-flash-lite',base_url:base,expected_version:0,api_key:key});
      if(JSON.stringify(staged).includes(key))throw new Error('Synthetic secret returned');
      const preview=await post(root+'/commands/preview',staged.command);
      const approved=await post(root+'/commands/approve',{proposal_id:preview.proposal_id,payload_hash:preview.payload_hash});
      await post(root+'/commands/commit',{proposal_id:preview.proposal_id,idempotency_key:crypto.randomUUID(),approval:approved.approval});
    }
    const status=await(await fetch(config+'/status')).json();
    const denied=await fetch(config+'/enable',{method:'POST',headers,body:JSON.stringify({candidate_id:status.candidate_id,version:status.version,confirm_network:true})});
    return {key_configured:status.key_configured,network_permitted:status.network_permitted,mode:status.mode,test_passed:status.test_passed,enable_denied:!denied.ok};
  },{base,save});
}
async function main(){
  fs.writeFileSync(file,JSON.stringify(source));
  try{
    phase='launch-explicit';let page=await launch({bases:[base],proxy:'http://127.0.0.1:7890'});
    phase='inspect-explicit';
    const permitted=await inspect(page,true);
    assert.deepEqual(permitted,{key_configured:true,network_permitted:true,mode:'offline',test_passed:false,enable_denied:true});
    phase='close-explicit';await app.close();app=null;
    phase='launch-default';
    page=await launch({bases:[],proxy:null});
    phase='inspect-default';const defaultState=await inspect(page,false);
    assert.deepEqual(defaultState,{key_configured:true,network_permitted:false,mode:'offline',test_passed:false,enable_denied:true});
    console.log('Synthetic desktop explicit transport reaches BCG/QG; restart default denies network; no Provider request');
  }finally{try{if(app)await app.close();}finally{fs.writeFileSync(file,original);}}
}
main().catch(error=>{console.error('Synthetic desktop model transport acceptance failed: '+phase+' '+String(error.message).slice(0,700));process.exitCode=1;});
