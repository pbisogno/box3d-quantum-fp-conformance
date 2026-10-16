import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {decodeKey,seal,sha256,MANIFEST} from './envelope.mjs';
import {approvedRunner} from './guards.mjs';
let scratch;
try {
  const args=process.argv.slice(2);
  if(args.length!==2||args[0]!=='--input')throw new Error('Invalid arguments');
  const {temp,workspace}=approvedRunner(), input=path.resolve(args[1]);
  if(path.dirname(input)!==temp||input===workspace||input.startsWith(workspace+path.sep)||fs.lstatSync(input).isSymbolicLink()||fs.realpathSync(input)!==input)throw new Error('Result directory must be below RUNNER_TEMP outside checkout');
  const key=decodeKey(process.env.BFP_PAYLOAD_KEY);delete process.env.BFP_PAYLOAD_KEY;
  try {
    scratch=fs.mkdtempSync(path.join(temp,'.bfp-results-'));fs.chmodSync(scratch,0o700);
    const zipPath=path.join(scratch,'results.zip'),tools=path.dirname(fileURLToPath(import.meta.url));
    const env={...process.env};delete env.BFP_PAYLOAD_KEY;
    const child=spawnSync('python3',['-B',path.join(tools,'pack_results.py'),'--input',input,'--output',zipPath],{encoding:'utf8',env,timeout:120000,maxBuffer:65536});
    if(child.error||child.status!==0)throw new Error('Result packing rejected');
    const detail=JSON.parse(child.stdout),zip=fs.readFileSync(zipPath);
    if(zip.length>8*1024*1024||zip.length!==detail.zip_bytes||sha256(zip)!==detail.zip_sha256)throw new Error('Archive size or hash mismatch');
    const encrypted=seal(zip,key,'results');zip.fill(0);
    const encoded=encrypted.toString('base64'),parts=Array.from({length:Math.ceil(encoded.length/19000)},(_,i)=>encoded.slice(i*19000,(i+1)*19000));
    const record={schema:'bfp-encrypted-results-v1',manifest_sha256:MANIFEST,encoding:'aes-256-gcm+base64',envelope_magic:'BFPRES01',cipher_bytes:encrypted.length,cipher_sha256:sha256(encrypted),zip_bytes:detail.zip_bytes,zip_sha256:detail.zip_sha256,plaintext_bytes:detail.plaintext_bytes,files:detail.files,chunks:parts.length,chunk_chars:19000,zip_cap_bytes:8*1024*1024};
    // No raw result or comparison contents are emitted. All payload chunks are ciphertext.
    console.log(JSON.stringify(record));
    for(let i=0;i<parts.length;i++)console.log(JSON.stringify({schema:'bfp-encrypted-results-chunk-v1',index:i,payload:parts[i]}));
  } finally {key.fill(0);}
} catch {process.stderr.write('Encrypted result archiving rejected; no plaintext diagnostics emitted\n');process.exitCode=1;}
finally {if(scratch)fs.rmSync(scratch,{recursive:true,force:true});}
