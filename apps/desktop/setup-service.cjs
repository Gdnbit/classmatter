// Private parent-owned stdio channel. No network listener, shell or renderer paths.
const {spawn}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const path=require('node:path');

function validRequest(value) {
  if(!value || typeof value!=='object' || Array.isArray(value))return false;
  const keys=Object.keys(value).sort().join(',');
  if(value.operation==='status')return keys==='operation';
  if(value.operation==='development_access')return keys==='operation';
  if(value.operation==='development_reauthenticate')return keys==='client,csrf,operation,session' && ['client','csrf','session'].every(name=>typeof value[name]==='string'&&/^[A-Za-z0-9_-]{32,128}$/.test(value[name]));
  if(['create_owner','preview_control'].includes(value.operation))return keys==='operation,password' && typeof value.password==='string' && value.password.length>=16 && value.password.length<=256;
  return value.operation==='approve_control' && keys==='confirmed,operation,operation_id,payload_hash' && value.confirmed===true && typeof value.operation_id==='string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value.operation_id) && typeof value.payload_hash==='string' && /^[a-f0-9]{64}$/.test(value.payload_hash);
}

class SetupPipe {
  constructor(child,key,timeout=15000) {
    this.child=child;this.key=key;this.timeout=timeout;this.pending=null;this.buffer='';this.closed=false;
    child.stdout.setEncoding('utf8');
    child.stdout.on('data',chunk=>{
      this.buffer+=chunk;
      if(Buffer.byteLength(this.buffer)>16384)return this.stop();
      let end;
      while((end=this.buffer.indexOf('\n'))>=0) {
        const line=this.buffer.slice(0,end);this.buffer=this.buffer.slice(end+1);
        let result;try {result=JSON.parse(line);} catch {this.stop();return;}
        const pending=this.pending;
        if(!pending || result?.id!==pending.id || typeof result.ok!=='boolean') {this.stop();return;}
        this.pending=null;clearTimeout(pending.timer);
        if(result.ok && Object.keys(result).sort().join(',')==='id,ok,result')pending.resolve(result.result);
        else pending.reject(new Error('setup_not_completed'));
      }
    });
    child.on('error',()=>this.stop());child.on('close',()=>this.stop());
    // Deliberately do not relay child output or exceptions to the UI/logs.
    child.stdin.on('error',()=>this.stop());
  }
  request(value) {
    if(!validRequest(value)||this.closed||this.pending)return Promise.reject(new Error('setup_not_completed'));
    const id=randomBytes(16).toString('hex');
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>this.stop(),this.timeout);
      this.pending={id,resolve,reject,timer};
      this.child.stdin.write(JSON.stringify({id,key:this.key,request:value})+'\n');
    });
  }
  stop() {
    if(this.closed)return;
    this.closed=true;this.key='';this.buffer='';
    if(this.pending){clearTimeout(this.pending.timer);this.pending.reject(new Error('setup_not_completed'));this.pending=null;}
    this.child.stdin.end();if(this.child.exitCode===null)this.child.kill();
  }
}

function setupService(repositoryRoot,runtimeRoot,development=false) {
  if(process.platform!=='win32'||!path.isAbsolute(repositoryRoot)||!path.isAbsolute(runtimeRoot))throw new Error('unsupported_setup');
  const key=randomBytes(32).toString('hex');
  const env={...process.env,CLASSMATTER_SETUP_PROCESS_KEY:key};delete env.PYTHONPATH;delete env.PYTHONHOME;
  const args=['-I',path.join(repositoryRoot,'backend/desktop_setup.py'),'--runtime-root',runtimeRoot];
  if(development===true)args.push('--development-no-password');
  const child=spawn(path.join(repositoryRoot,'backend/.venv/Scripts/python.exe'),args,{cwd:repositoryRoot,env,shell:false,windowsHide:true,stdio:['pipe','pipe','ignore']});
  return new SetupPipe(child,key);
}
module.exports={SetupPipe,setupService,validRequest};
