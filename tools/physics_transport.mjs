// Isolated physics transport; does not change the frozen kernel proof envelope.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createCipheriv, createDecipheriv, createHash, randomBytes} from 'node:crypto';
import {approvedRunner, isolatedNewChild} from './guards.mjs';
import {decodeKey} from './envelope.mjs';
const hash = b => createHash('sha256').update(b).digest('hex');
const cap = 16 * 1024 * 1024;
function context() {
  const runner = approvedRunner();
  const metadata = JSON.parse(fs.readFileSync(path.join(runner.workspace, 'protected/physics-metadata.json'), 'utf8'));
  if(metadata.schema !== 'bfp-physics-payload-v1' || !/^[0-9a-f]{64}$/.test(metadata.manifest_sha256)) throw new Error('Invalid physics manifest');
  return {...runner, metadata};
}
function envelope(plain, key, manifest, kind) {
  const nonce=randomBytes(12), cipher=createCipheriv('aes-256-gcm',key,nonce);
  cipher.setAAD(Buffer.from(`BFP-PHYSICS-${kind}-V1:${manifest}`,'ascii'));
  const data=Buffer.concat([cipher.update(plain),cipher.final()]);
  return Buffer.concat([Buffer.from(kind==='SOURCES'?'BFPPHY01':'BFPPHR01','ascii'),nonce,cipher.getAuthTag(),data]);
}
function decrypt(raw,key,manifest) {
  if(raw.length<36||raw.length>cap||raw.subarray(0,8).toString('ascii')!=='BFPPHY01') throw new Error('Invalid source envelope');
  const cipher=createDecipheriv('aes-256-gcm',key,raw.subarray(8,20));
  cipher.setAAD(Buffer.from(`BFP-PHYSICS-SOURCES-V1:${manifest}`,'ascii'));cipher.setAuthTag(raw.subarray(20,36));
  return Buffer.concat([cipher.update(raw.subarray(36)),cipher.final()]);
}
try {
  const command=process.argv[2], ctx=context(), key=decodeKey(process.env.BFP_PAYLOAD_KEY ?? '');
  try {
    if(command==='restore' && process.argv.length===3) {
      const out=isolatedNewChild(path.join(ctx.temp,'bfp-physics-payload'),ctx.temp,ctx.workspace);
      const raw=fs.readFileSync(path.join(ctx.workspace,'protected/physics.aesgcm'));
      if(raw.length!==ctx.metadata.cipher_bytes||hash(raw)!==ctx.metadata.cipher_sha256)throw new Error('Cipher identity mismatch');
      const zip=decrypt(raw,key,ctx.metadata.manifest_sha256);
      if(zip.length!==ctx.metadata.zip_bytes||hash(zip)!==ctx.metadata.zip_sha256)throw new Error('ZIP identity mismatch');
      const zipPath=path.join(ctx.temp,'bfp-physics-sources.zip');
      fs.writeFileSync(zipPath,zip,{flag:'wx',mode:0o600});zip.fill(0);
      const env={PATH:process.env.PATH,LANG:'C.UTF-8',PYTHONDONTWRITEBYTECODE:'1'};
      const run=spawnSync('python3',['-B',path.join(ctx.workspace,'tools/physics_runner.py'),'extract',zipPath,out],{env,stdio:['ignore','pipe','pipe'],maxBuffer:1024*1024});
      if(run.status!==0)throw new Error('Source extraction rejected');
      process.stdout.write(JSON.stringify({schema:'bfp-physics-restored-v1',manifest_sha256:ctx.metadata.manifest_sha256,arch:ctx.expectedArch})+'\n');
    } else if(command==='archive' && process.argv.length===3) {
      const zipPath=path.join(ctx.temp,'bfp-physics-results.zip');
      const run=spawnSync('python3',['-B',path.join(ctx.workspace,'tools/physics_runner.py'),'pack',path.join(ctx.temp,'bfp-physics-build'),zipPath],{env:{PATH:process.env.PATH,LANG:'C.UTF-8',PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe'],maxBuffer:1024*1024});
      if(run.status!==0)throw new Error('Result pack rejected');
      const meta=JSON.parse(run.stdout.toString('utf8')),zip=fs.readFileSync(zipPath);
      if(zip.length>cap||zip.length!==meta.zip_bytes||hash(zip)!==meta.zip_sha256)throw new Error('Result ZIP invalid');
      const raw=envelope(zip,key,ctx.metadata.manifest_sha256,'RESULTS');zip.fill(0);
      const chunks=raw.toString('base64').match(/.{1,19000}/g);
      process.stdout.write(JSON.stringify({schema:'bfp-physics-results-v1',arch:ctx.expectedArch,manifest_sha256:ctx.metadata.manifest_sha256,cipher_bytes:raw.length,cipher_sha256:hash(raw),chunks:chunks.length,...meta})+'\n');
      for(let i=0;i<chunks.length;i++)process.stdout.write(JSON.stringify({schema:'bfp-physics-results-chunk-v1',index:i,payload:chunks[i]})+'\n');
    } else throw new Error('Invalid transport command');
  } finally { key.fill(0); }
} catch {
  process.stderr.write('Physics transport rejected; no plaintext diagnostics logged.\n');process.exitCode=1;
}
