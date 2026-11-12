import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
const base=process.env.CLASS_OS_TEST_URL;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base||''))throw Error('Owned synthetic fixture required');
const browser=await chromium.launch({headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'],...(process.platform==='win32'?{channel:'msedge'}:{})});
let page;
try{
 const context=await browser.newContext({viewport:{width:1440,height:900},permissions:['microphone']});
 page=await context.newPage();const errors=[],captured=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(()=>{
  const start=MediaRecorder.prototype.start;
  MediaRecorder.prototype.start=function(...args){window.__recordedBytes=0;this.addEventListener('dataavailable',event=>window.__recordedBytes+=event.data.size);return start.apply(this,args);};
  const later=window.setTimeout.bind(window);
  window.setTimeout=(fn,delay,...args)=>later(fn,delay===180000&&window.__testAutomaticStop?1400:delay,...args);
 });
 await page.goto(base);await page.getByLabel('密码',{exact:true}).fill('synthetic-test-passphrase-2026');await page.getByRole('button',{name:'登录',exact:true}).click();
 const input=page.getByLabel('输入消息'),pending=page.getByRole('group',{name:'待识别录音'});
 await input.waitFor();
 async function record(){await page.getByRole('button',{name:'语音转文字',exact:true}).click();await page.getByRole('button',{name:'完成录音并转文字',exact:true}).waitFor();await page.waitForFunction(()=>window.__recordedBytes>0);}
 let fail=true;
 await page.route('**/composer/capture',async route=>{captured.push(route.request().postDataJSON());if(fail)await route.fulfill({status:503,contentType:'application/json',body:'{"error":"capture_failed"}'});else await route.continue();});
 await input.fill('原始草稿');await record();await page.getByRole('button',{name:'完成录音并转文字',exact:true}).click();
 await pending.waitFor();assert.equal(await input.inputValue(),'原始草稿');assert.equal(captured.length,1);
 fail=false;await pending.getByRole('button',{name:'识别录音',exact:true}).dblclick();
 await page.waitForFunction(()=>document.querySelector('textarea').value==='原始草稿\n合成识别文字');await pending.waitFor({state:'hidden'});
 assert.equal(captured.length,2,'A double click cannot duplicate transcription');assert.equal(captured[0].data,captured[1].data,'Retry uses the same recorded bytes');
 // A failed clip on the unallocated new chat follows its actual newly saved thread.
 fail=true;await record();await page.getByRole('button',{name:'完成录音并转文字',exact:true}).click();await pending.waitFor();
 await input.fill('带录音的聊天');await page.getByRole('button',{name:'发送消息',exact:true}).click();await page.getByText('合成回复已完成',{exact:true}).waitFor();
 const original=page.url();await pending.waitFor();await input.fill('原对话未发送文字');
 await page.getByRole('button',{name:'新对话',exact:true}).click();await input.fill('另一对话草稿');assert.equal(await pending.count(),0);
 await page.getByRole('region',{name:'聊天列表'}).getByRole('button',{name:'带录音的聊天',exact:true}).click();await page.waitForURL(original);await pending.waitFor();assert.equal(await input.inputValue(),'原对话未发送文字');
 page.once('dialog',dialog=>{assert.match(dialog.message(),/无法恢复/);void dialog.dismiss();});await pending.getByRole('button',{name:'丢弃录音',exact:true}).click();await pending.waitFor();
 page.once('dialog',dialog=>void dialog.accept());await pending.getByRole('button',{name:'丢弃录音',exact:true}).click();await pending.waitFor({state:'hidden'});
 // Leaving a live recording retains the origin clip without uploading it into another chat.
 const beforeNavigation=captured.length;await record();await page.getByRole('button',{name:'新对话',exact:true}).click();await input.fill('另一对话草稿');await page.waitForTimeout(500);assert.equal(captured.length,beforeNavigation);assert.equal(await input.inputValue(),'另一对话草稿');
 await page.getByRole('region',{name:'聊天列表'}).getByRole('button',{name:'带录音的聊天',exact:true}).click();await page.waitForURL(original);await pending.waitFor();assert.equal(await input.inputValue(),'原对话未发送文字');
 fail=false;await pending.getByRole('button',{name:'识别录音',exact:true}).click();await page.waitForFunction(()=>document.querySelector('textarea').value==='原对话未发送文字\n合成识别文字');await pending.waitFor({state:'hidden'});
 // Late ASR after navigation cannot append to either the wrong chat or the original draft.
 let release;const held=new Promise(resolve=>release=resolve);let requestStarted;
 const started=new Promise(resolve=>requestStarted=resolve);
 await page.unroute('**/composer/capture');await page.route('**/composer/capture',async route=>{requestStarted();await held;await route.fulfill({status:200,contentType:'application/json',body:'{"schema_version":"classmatter.composer-capture.v1","text":"迟到的转写"}'}).catch(()=>{});});
 await record();await page.getByRole('button',{name:'完成录音并转文字',exact:true}).click();await started;
 const originText=await input.inputValue();await page.getByRole('button',{name:'新对话',exact:true}).click();await input.fill('保持新对话');release();await page.waitForTimeout(700);assert.equal(await input.inputValue(),'保持新对话');
 await page.getByRole('region',{name:'聊天列表'}).getByRole('button',{name:'带录音的聊天',exact:true}).click();await page.waitForURL(original);await pending.waitFor();assert.equal(await input.inputValue(),originText);
 await page.unroute('**/composer/capture');await pending.getByRole('button',{name:'识别录音',exact:true}).click();await page.waitForFunction(text=>document.querySelector('textarea').value===text+'\n合成识别文字',originText);await pending.waitFor({state:'hidden'});
 // Timer is sped up only in this test; the actual configured duration remains three minutes.
 await page.evaluate(()=>window.__testAutomaticStop=true);await page.getByRole('button',{name:'语音转文字',exact:true}).click();await page.waitForFunction(text=>document.querySelector('textarea').value===text+'\n合成识别文字\n合成识别文字',originText);await pending.waitFor({state:'hidden'});
 await page.evaluate(()=>window.__testAutomaticStop=false);
 // Unmounting the composer on a different page retains the clip in the original chat.
 const beforePageLeave=captured.length,oldDraft=await input.inputValue();await record();await page.getByRole('button',{name:'学生',exact:true}).click();await page.waitForTimeout(300);
 await page.getByRole('region',{name:'聊天列表'}).getByRole('button',{name:'带录音的聊天',exact:true}).click();await page.waitForURL(original);await pending.waitFor();assert.equal(await input.inputValue(),oldDraft);assert.equal(captured.length,beforePageLeave);
 page.once('dialog',dialog=>void dialog.accept());await pending.getByRole('button',{name:'丢弃录音',exact:true}).click();await pending.waitFor({state:'hidden'});
 // The bounded in-memory queue refuses a sixth clip before requesting the microphone.
 await page.route('**/composer/capture',route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"capture_failed"}'}));
 for(let i=0;i<5;i++){
  await page.getByRole('button',{name:'新对话',exact:true}).click();await record();await page.getByRole('button',{name:'完成录音并转文字',exact:true}).click();await pending.waitFor();
  await input.fill(`限额录音${i}`);await page.getByRole('button',{name:'发送消息',exact:true}).click();await page.getByText('合成回复已完成',{exact:true}).waitFor();await pending.waitFor();
 }
 await page.getByRole('button',{name:'新对话',exact:true}).click();await page.getByRole('button',{name:'语音转文字',exact:true}).click();await page.getByRole('alert').filter({hasText:'请先处理已有录音'}).waitFor();assert.equal(await page.getByRole('button',{name:'完成录音并转文字',exact:true}).count(),0);
 await page.getByRole('region',{name:'聊天列表'}).getByRole('button',{name:'限额录音0',exact:true}).click();await pending.waitFor();page.once('dialog',dialog=>void dialog.accept());await pending.getByRole('button',{name:'丢弃录音',exact:true}).click();await pending.waitFor({state:'hidden'});
 await page.getByRole('button',{name:'新对话',exact:true}).click();await record();page.once('dialog',dialog=>void dialog.accept());await page.getByRole('button',{name:'取消识别',exact:true}).click();assert.equal(await pending.count(),0);
 assert.deepEqual(errors,[]);console.log('PASS recording recovery: exact retry, no double append, new-thread transfer, discard consequence, navigation and late-result isolation, bounded automatic stop');
}catch(error){console.error('Recording recovery failed',await page?.locator('body').innerText());throw error;}finally{await browser.close();}
