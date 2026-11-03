'use strict';
const el=id=>document.getElementById(id),api=window.classMatterSetup;
let owner=false,proposal=null;
async function perform(work) {
  el('error').textContent='';document.querySelectorAll('button').forEach(button=>button.disabled=true);
  try {await work();} catch {el('error').textContent='本次设置未完成。请核对密码和本机服务；没有自动重置或重新执行。若创建后未收到恢复码，请使用原身份恢复码重发流程。';}
  finally {document.querySelectorAll('button').forEach(button=>button.disabled=false);el('recovery-next').disabled=!el('saved').checked;}
}
function askPassword(existing) {
  owner=existing;el('password-form').hidden=false;el('repeat-label').hidden=existing;
  el('password').autocomplete=existing?'current-password':'new-password';
  el('repeat').required=!existing;el('password-submit').textContent=existing?'验证并查看初始化预览':'设置并继续';
  el('status').textContent=existing?'本机身份已建立。请本人验证后确认会话初始化。':'首次使用，请本人设置本机密码。';
}
el('password-form').addEventListener('submit',event=>{
  event.preventDefault();const password=el('password').value,repeat=el('repeat').value;
  el('password').value='';el('repeat').value='';
  if(!owner&&password!==repeat){el('error').textContent='两次密码不一致，请重新输入。';return;}
  void perform(async()=>{
    if(!owner){const result=await api.createOwner(password);owner=true;el('codes').textContent=result.recovery_codes.join('\n');el('password-form').hidden=true;el('recovery').hidden=false;}
    else {proposal=await api.preview(password);el('password-form').hidden=true;el('payload').textContent=JSON.stringify(proposal.payload,null,2);el('hash').textContent='风险 '+proposal.risk+' · 摘要 '+proposal.payload_hash;el('preview').hidden=false;}
  });
});
el('saved').addEventListener('change',()=>el('recovery-next').disabled=!el('saved').checked);
el('recovery-next').addEventListener('click',()=>{if(!el('saved').checked)return;el('codes').textContent='';el('recovery').hidden=true;askPassword(true);});
el('approve').addEventListener('click',()=>void perform(async()=>{
  await api.approve(proposal.operation_id,proposal.payload_hash);el('preview').hidden=true;el('status').textContent='本机设置完成。';el('continue').hidden=false;
}));
el('continue').addEventListener('click',()=>void perform(()=>api.continue()));
void perform(async()=>{const state=await api.status();if(state.ready){el('status').textContent='本机设置已完成。';el('continue').hidden=false;}else askPassword(state.owner_present);});
