const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const stage=path.resolve(__dirname,'../.build/runtime');
if(!fs.existsSync(path.join(stage,'ui/desktop-runtime.json'))) {console.error('Build the runtime first.');process.exit(1);}
const source=JSON.parse(fs.readFileSync(path.join(stage,'runtime-source.json'),'utf8'));
if(typeof source.repositoryRoot!=='string' || typeof source.runtimeRoot!=='string' || path.resolve(source.runtimeRoot)!==path.join(path.resolve(source.repositoryRoot),'.local-runtime/synthetic-v1')) {
  console.error('Rebuild the runtime before launch; an integration fixture descriptor is not a user profile.');process.exit(1);
}
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(require('electron'),[stage],{stdio:'ignore',env,windowsHide:true});
child.on('error',()=>{console.error('Desktop runtime could not start.');process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code||0;});
