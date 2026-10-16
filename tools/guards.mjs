import fs from 'node:fs';
import path from 'node:path';
export function approvedRunner() {
  const e=process.env;
  if(e.GITHUB_ACTIONS!=='true'||process.platform!=='linux'||process.arch!=='x64'||e.GITHUB_REPOSITORY!=='pbisogno/box3d-quantum-fp-conformance'||e.GITHUB_REPOSITORY_VISIBILITY!=='public'||e.GITHUB_REF!=='refs/heads/main'||e.GITHUB_EVENT_NAME!=='workflow_dispatch') throw new Error('Requires the approved public Linux x64 manual main-branch runner');
  const event=JSON.parse(fs.readFileSync(e.GITHUB_EVENT_PATH,'utf8'));
  if(event.repository?.full_name!==e.GITHUB_REPOSITORY||event.repository?.private!==false||event.repository?.visibility!=='public'||event.repository?.default_branch!=='main') throw new Error('Repository event identity mismatch');
  const temp=fs.realpathSync(e.RUNNER_TEMP), workspace=fs.realpathSync(e.GITHUB_WORKSPACE);
  if(temp===workspace||temp.startsWith(workspace+path.sep)) throw new Error('Runner temporary directory must be outside checkout');
  return {temp,workspace};
}
export function isolatedNewChild(value,temp,workspace) {
  const out=path.resolve(value);
  if(path.dirname(out)!==temp||out===workspace||out.startsWith(workspace+path.sep)||fs.existsSync(out)) throw new Error('Output must be a new direct child of RUNNER_TEMP outside checkout');
  return out;
}
