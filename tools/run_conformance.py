"""DRAFT public Linux x64 CI adapter. No installs, raw log dumps or artifacts.

This file is prepared locally only. The entire unchanged private payload is
decrypted by a separate reviewed Node tool into RUNNER_TEMP, never this tree.
The comparator and C wire schemas remain frozen compatibility schemas.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

MANIFEST_SHA256='8d7708a1b7aeb04d2c91955d95392b77a8d7dd86762b7a34a8d3ed08efaf59ab'
PROFILES={
    'gcc-o0':('gcc',['-O0']),
    'gcc-o2':('gcc',['-O2']),
    'clang-o2':('clang',['-O2']),
    'gcc-ubsan':('gcc',['-O1','-g','-fsanitize=undefined','-fno-sanitize-recover=all'])}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def emit(record):print(json.dumps(record,sort_keys=True),flush=True)

def channel_record(text):
    raw=text.encode('utf-8')
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),text_emitted=False)

def child_run(command,timeout,env):
    try:return subprocess.run(command,capture_output=True,text=True,timeout=timeout,env=env)
    except subprocess.TimeoutExpired as error:
        def as_text(x):return x.decode('utf-8',errors='replace') if isinstance(x,bytes) else x or ''
        return SimpleNamespace(returncode=124,stdout=as_text(error.stdout),stderr=as_text(error.stderr))
    except OSError:
        return SimpleNamespace(returncode=127,stdout='',stderr='PUBLIC_RUNNER_OS_ERROR')

def manifest_check(root):
    if sha(root/'manifest.json')!=MANIFEST_SHA256:raise ValueError('immutable original manifest hash')
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if manifest['schema']!='private-qfp-conformance-bundle-v1':raise ValueError('original manifest schema')
    if manifest['raw_precision']!=16 or manifest['mul_round']!=32768 or manifest['unique_requests']!=83290:
        raise ValueError('frozen numerical/corpus identity')
    files=manifest['files'];names={row['path'] for row in files}
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.relative_to(root).as_posix()!='manifest.json'}
    if len(names)!=len(files) or names!=actual:raise ValueError('manifest inventory')
    for row in files:
        relative=PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in row['path']:raise ValueError('unsafe relative path')
        path=root/row['path']
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('unsafe payload file')
        if path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('payload content identity')
    return manifest,sha(root/'manifest.json')

def public_comparison(comparison):
    # No expected_case, actual_case, operand, raw_prefix or exception message is
    # emitted. Full ordered typed comparison still occurs in the frozen module.
    count=comparison.get('compared',0);issues=comparison.get('issue_count',1)
    statuses=comparison.get('status_counts',{})
    if type(count)is not int or type(issues)is not int or type(statuses)is not dict:
        raise ValueError('comparison projection types')
    clean={}
    for key,value in statuses.items():
        if key not in {str(i) for i in range(8)} or type(value)is not int or value<0:
            raise ValueError('status projection')
        clean[key]=value
    return dict(passed=comparison.get('passed')is True,compared=count,issue_count=issues,status_counts=clean)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--visibility',choices=['public'],required=True)
    parser.add_argument('--payload-dir',required=True)
    parser.add_argument('--build-dir',required=True)
    parser.add_argument('--profiles',default=','.join(PROFILES))
    args=parser.parse_args()
    if (os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
        or os.environ.get('GITHUB_REPOSITORY_VISIBILITY')!='public'
        or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted'
        or platform.system()!='Linux' or platform.machine().lower()not in ('x86_64','amd64')):
        raise ValueError('public manual GitHub-hosted Linux x64 only')
    if args.profiles.split(',')!=list(PROFILES):raise ValueError('exact four frozen profiles required')
    temp=Path(os.environ['RUNNER_TEMP']).resolve();out=Path(args.build_dir).resolve()
    root=Path(args.payload_dir).resolve()
    if (out==temp or root==temp or temp not in out.parents or temp not in root.parents
        or out==root or out.parent!=root.parent or root in out.parents or out in root.parents):
        raise ValueError('payload/build must be distinct sibling directories below RUNNER_TEMP')
    manifest,manifest_sha=manifest_check(root)
    # Workflow checks this module and comparator hashes before Python payload
    # execution; this second inventory gate is before importing the comparator.
    spec=importlib.util.spec_from_file_location('verified_frozen_comparator',root/'tools/compare_native.py')
    if spec is None or spec.loader is None:raise ValueError('verified comparator loading')
    comparator=importlib.util.module_from_spec(spec);spec.loader.exec_module(comparator)
    compare=comparator.compare
    out.mkdir(parents=True,exist_ok=True)
    # Keep runtime scratch outside the strict results-packer build inventory.
    # Both scratch paths must be fresh siblings, never existing/symlink dirs.
    home=out.with_name(out.name+'-home');scratch=out.with_name(out.name+'-tmp')
    if home.exists() or home.is_symlink() or scratch.exists() or scratch.is_symlink():
        raise ValueError('runtime HOME/TMPDIR siblings must be new paths')
    home.mkdir(mode=0o700,exist_ok=False);scratch.mkdir(mode=0o700,exist_ok=False)
    env=dict(PATH=os.environ['PATH'],HOME=str(home),TMPDIR=str(scratch),
             LANG='C',LC_ALL='C',TZ='UTC',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=0')
    deadline=time.monotonic()+600
    results=[]
    for name,(compiler,flags) in PROFILES.items():
        executable=shutil.which(compiler)
        if not executable:raise ValueError('required preinstalled compiler unavailable')
        directory=out/name;directory.mkdir(exist_ok=True)
        remaining=deadline-time.monotonic()
        if remaining<=0:
            row=dict(schema='public-qfp-native-profile-v1',profile=name,passed=False,stage='overall_timeout',exit_code=124)
            results.append(row);emit(row)
            continue
        version=child_run([executable,'--version'],min(10,remaining),env)
        if version.returncode:raise ValueError('compiler version query failed')
        (directory/'compiler-version.stdout').write_text(version.stdout,encoding='utf-8')
        (directory/'compiler-version.stderr').write_text(version.stderr,encoding='utf-8')
        binary=directory/'fp-conformance'
        command=[executable,'-std=c17','-pedantic-errors','-Wall','-Wextra',*flags,
                 str(root/'src/fp-conformance.c'),str(root/'src/fp.c'),'-o',str(binary)]
        (directory/'compile-command.json').write_text(json.dumps(command)+'\n',encoding='utf-8')
        begin=time.monotonic()
        remaining=deadline-time.monotonic()
        if remaining<=0:
            row=dict(schema='public-qfp-native-profile-v1',profile=name,passed=False,stage='overall_timeout',exit_code=124)
            results.append(row);emit(row)
            continue
        build=child_run(command,min(120,remaining),env)
        (directory/'compile.stdout').write_text(build.stdout,encoding='utf-8')
        (directory/'compile.stderr').write_text(build.stderr,encoding='utf-8')
        row=dict(schema='public-qfp-native-profile-v1',profile=name,compiler=compiler,
                 compiler_version_sha256=hashlib.sha256(version.stdout.encode()).hexdigest(),
                 compile_exit=build.returncode,compile_stdout=channel_record(build.stdout),
                 compile_stderr=channel_record(build.stderr))
        if build.returncode:row.update(passed=False,stage='compile')
        elif deadline-time.monotonic()<=0:row.update(passed=False,stage='overall_timeout',run_exit=124)
        else:
            actual=directory/'actual.jsonl'
            execution=child_run([str(binary),'--lut-dir',str(root/'lut'),'--input',str(root/'vectors/requests.tsv'),
                                 '--output',str(actual)],min(120,deadline-time.monotonic()),env)
            (directory/'run.stdout').write_text(execution.stdout,encoding='utf-8')
            (directory/'run.stderr').write_text(execution.stderr,encoding='utf-8')
            try:
                comparison=compare(root/'vectors/expected.jsonl',actual) if actual.exists() else dict(passed=False,compared=0,issue_count=1,status_counts={})
            except (OSError,ValueError,TypeError,KeyError,AttributeError):
                comparison=dict(passed=False,compared=0,issue_count=1,status_counts={})
            projection=public_comparison(comparison)
            (directory/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n',encoding='utf-8')
            row.update(stage='compare',run_exit=execution.returncode,
                run_stdout=channel_record(execution.stdout),run_stderr=channel_record(execution.stderr),
                actual_sha256=sha(actual) if actual.exists() else None,
                binary_sha256=sha(binary),comparison=projection,
                passed=execution.returncode==0 and not execution.stdout.strip() and not execution.stderr.strip()
                    and projection['passed'] and projection['compared']==manifest['unique_requests'])
        row['elapsed_seconds']=time.monotonic()-begin
        results.append(row);emit(row)
    summary=dict(schema='public-qfp-native-run-v1',manifest_sha256=manifest_sha,
        expected_requests_per_profile=manifest['unique_requests'],profiles=len(results),
        runtime_arch=platform.machine(),runtime_os=platform.system(),
        passed=len(results)==4 and all(r['passed'] for r in results),results=results,
        raw_output_logged=False,arbitrary_channel_text_logged=False,artifacts_uploaded=False,caches_used=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    emit({key:summary[key] for key in ('schema','manifest_sha256','expected_requests_per_profile','profiles','passed')})
    return 0 if summary['passed'] else 1

if __name__=='__main__':
    try:code=main()
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        emit(dict(schema='public-qfp-native-run-v1',passed=False,stage='preflight_or_io',reason_code='VALIDATION_FAILED'))
        code=1
    raise SystemExit(code)
