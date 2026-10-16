import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {decodeKey,open,sha256,MANIFEST} from './envelope.mjs';
import {approvedRunner,isolatedNewChild} from './guards.mjs';
let scratch;
try {
  const args=process.argv.slice(2);
  if(args.length!==4||args[0]!=='--input'||args[2]!=='--output')throw new Error('Invalid arguments');
  const {temp,workspace}=approvedRunner(), out=isolatedNewChild(args[3],temp,workspace);
  const tools=path.dirname(fileURLToPath(import.meta.url));
  const input=path.resolve(args[1]);
  if(fs.lstatSync(input).isSymbolicLink())throw new Error('Input symlink rejected');
  const metaPath=path.join(path.dirname(input),'payload-metadata.json');
  const metadata=JSON.parse(fs.readFileSync(metaPath,'utf8'));
  if(metadata.schema!=='bfp-encrypted-payload-v1'||metadata.manifest_sha256!==MANIFEST)throw new Error('Metadata identity mismatch');
  if(!Number.isSafeInteger(metadata.cipher_bytes)||metadata.cipher_bytes<36||metadata.cipher_bytes>32*1024*1024||fs.statSync(input).size!==metadata.cipher_bytes)throw new Error('Cipher size rejected');
  const encrypted=fs.readFileSync(input);
  if(sha256(encrypted)!==metadata.cipher_sha256)throw new Error('Cipher digest mismatch');
  const key=decodeKey(process.env.BFP_PAYLOAD_KEY);
  let zip;
  try {zip=open(encrypted,key,'payload');}finally{key.fill(0);delete process.env.BFP_PAYLOAD_KEY;}
  if(zip.length!==metadata.zip_bytes||sha256(zip)!==metadata.zip_sha256)throw new Error('ZIP identity mismatch');
  scratch=fs.mkdtempSync(path.join(temp,'.bfp-decrypt-'));fs.chmodSync(scratch,0o700);
  const zipPath=path.join(scratch,'payload.zip');fs.writeFileSync(zipPath,zip,{mode:0o600,flag:'wx'});zip.fill(0);
  const env={...process.env};delete env.BFP_PAYLOAD_KEY;
  const child=spawnSync('python3',['-B',path.join(tools,'extract_payload.py'),'--zip',zipPath,'--metadata',metaPath,'--output',out,'--public-src',path.join(workspace,'src')],{encoding:'utf8',env,timeout:60000,maxBuffer:16384});
  if(child.error||child.status!==0)throw new Error('Authenticated extraction rejected');
  process.stdout.write(child.stdout);
} catch {process.stderr.write('Encrypted payload restoration rejected\n');process.exitCode=1;}
finally {if(scratch)fs.rmSync(scratch,{recursive:true,force:true});}
