const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const desktop=path.resolve(__dirname,'..'),root=path.resolve(desktop,'../..'),web=path.join(root,'apps/web'),stage=path.join(desktop,'.build/runtime');
for(const name of ['identity','model-configuration','agent-conversation','command-receipts']) {
  const result=spawnSync(process.execPath,[path.join(web,'scripts',`generate-${name}.mjs`),'--check'],{cwd:web,stdio:'inherit'});
  if(result.status!==0)process.exit(1);
}
const result=spawnSync(process.execPath,[path.join(web,'node_modules/vite/bin/vite.js'),'build','--outDir',path.join(stage,'ui'),'--emptyOutDir'],{cwd:web,stdio:'inherit',env:{...process.env,VITE_CLASS_OS_DEMO:'false',VITE_CLASS_OS_DESKTOP:'true',FIGMA_PUBLIC_URL:''}});
if(result.status!==0)process.exit(1);
fs.mkdirSync(stage,{recursive:true});
fs.copyFileSync(path.join(desktop,'runtime-main.cjs'),path.join(stage,'main.cjs'));
for(const file of ['runtime-service.cjs','runtime-policy.cjs','preload.cjs'])fs.copyFileSync(path.join(desktop,file),path.join(stage,file));
fs.writeFileSync(path.join(stage,'package.json'),JSON.stringify({name:'classmatter-synthetic-runtime',version:'0.1.0',main:'main.cjs'}));
fs.writeFileSync(path.join(stage,'runtime-source.json'),JSON.stringify({schema_version:1,repositoryRoot:root,runtimeRoot:path.join(root,'.local-runtime/synthetic-v1')}));
fs.writeFileSync(path.join(stage,'ui/desktop-runtime.json'),JSON.stringify({mode:'synthetic-runtime'}));
console.log('Built development-only R1 runtime assets; no database or service started.');
