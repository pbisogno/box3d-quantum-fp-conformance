"""Public native Linux x64/explicit ARM64 CI adapter. No raw dumps/artifacts.

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
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

MANIFEST_SHA256='8d7708a1b7aeb04d2c91955d95392b77a8d7dd86762b7a34a8d3ed08efaf59ab'
PROFILES={
    'gcc-o0':('gcc',['-O0']),
    'gcc-o2':('gcc',['-O2']),
    'clang-o2':('clang',['-O2']),
    'gcc-ubsan':('gcc',['-O1','-g','-fsanitize=undefined','-fno-sanitize-recover=all'])}
BASE_C_FLAGS=['-std=c17','-pedantic-errors','-Wall','-Wextra']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def emit(record):print(json.dumps(record,sort_keys=True),flush=True)

def channel_record(text):
    raw=text.encode('utf-8')
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),text_emitted=False)

def approved_architecture(env,system,machine):
    expected=env.get('BFP_EXPECTED_ARCH')
    aliases={'x64':('x86_64','amd64'),'arm64':('aarch64','arm64')}
    runners={'x64':'X64','arm64':'ARM64'}
    if expected not in aliases or system!='Linux' or machine.lower() not in aliases[expected] or env.get('RUNNER_ARCH')!=runners[expected] or env.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise ValueError('Native hosted architecture does not match authorized x64/arm64 scope')
    return expected

def host_text(value):
    if type(value)is not str or len(value)>4096 or not value.isascii() or any(not c.isprintable() for c in value):
        raise ValueError('Host metadata must be bounded printable ASCII')
    return value

def cpu_fields(text):
    names={'model name':'model_name','cpu implementer':'cpu_implementer','cpu part':'cpu_part',
           'cpu architecture':'cpu_architecture','features':'features'}
    result={v:None for v in names.values()}
    for line in text.splitlines():
        key,sep,value=line.partition(':');key=key.strip().lower()
        if sep and key in names and result[names[key]] is None:
            result[names[key]]=host_text(value.strip())
    return result

def runtime_metadata(expected):
    if approved_architecture(os.environ,platform.system(),platform.machine())!=expected:
        raise ValueError('Host architecture changed')
    if sys.byteorder!='little' or struct.calcsize('P')*8!=64:
        raise ValueError('Only native little-endian 64-bit hosts are authorized')
    with Path('/proc/cpuinfo').open(encoding='ascii',errors='strict') as stream:
        cpu=cpu_fields(stream.read(1024*1024))
    count=os.cpu_count()
    if count is not None and (type(count)is not int or count<=0):raise ValueError('Invalid logical CPU count')
    return dict(expected_arch=expected,system='Linux',machine=host_text(platform.machine()),
        runner_arch=os.environ['RUNNER_ARCH'],runner_environment='github-hosted',byteorder=sys.byteorder,
        pointer_bits=struct.calcsize('P')*8,kernel_release=host_text(platform.release()),
        kernel_version=host_text(platform.version()),logical_cpus=count,cpu_fields=cpu)

def compiler_target_architecture(text):
    target=text.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',target):raise ValueError('Invalid compiler target triple')
    machine=target.split('-',1)[0].lower()
    if machine in ('x86_64','amd64'):return target,'x64'
    if machine in ('aarch64','arm64'):return target,'arm64'
    raise ValueError('Compiler target is not authorized x64/arm64')

def elf_metadata(raw,expected):
    if expected not in ('x64','arm64') or len(raw)<64 or raw[:4]!=b'\x7fELF' or raw[4:7]!=bytes((2,1,1)):
        raise ValueError('Expected native little-endian ELF64')
    machine=int.from_bytes(raw[18:20],'little');wanted={'x64':62,'arm64':183}[expected]
    if int.from_bytes(raw[16:18],'little') not in (2,3) or int.from_bytes(raw[20:24],'little')!=1 or machine!=wanted:
        raise ValueError('ELF executable target differs from authorized host')
    return dict(class_bits=64,byteorder='little',e_machine=machine,expected_e_machine=wanted,matches_expected_arch=True)

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
    expected_arch=approved_architecture(os.environ,platform.system(),platform.machine())
    if (os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
        or os.environ.get('GITHUB_REPOSITORY_VISIBILITY')!='public'
        or os.environ.get('GITHUB_REPOSITORY')!='pbisogno/box3d-quantum-fp-conformance'
        or os.environ.get('GITHUB_REF')!='refs/heads/main'):
        raise ValueError('approved public manual GitHub-hosted main-branch runner only')
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'));repo=event['repository']
    if repo['full_name']!=os.environ['GITHUB_REPOSITORY'] or repo['private'] is not False or repo['visibility']!='public' or repo['default_branch']!='main':
        raise ValueError('Repository event identity mismatch')
    runtime=runtime_metadata(expected_arch)
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
            row=dict(schema='public-qfp-native-profile-v1',profile=name,passed=False,stage='overall_timeout',exit_code=124,
                expected_arch=expected_arch,c_flags=BASE_C_FLAGS+flags,compiler_target=None,compiler_target_arch=None,elf=None)
            results.append(row);emit(row)
            continue
        version=child_run([executable,'--version'],min(10,remaining),env)
        if version.returncode:raise ValueError('compiler version query failed')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('Overall deadline before compiler target query')
        target=child_run([executable,'-dumpmachine'],min(10,remaining),env)
        (directory/'compiler-version.stdout').write_text(version.stdout+'\nBFP_DUMPMACHINE\n'+target.stdout,encoding='utf-8')
        (directory/'compiler-version.stderr').write_text(version.stderr+'\nBFP_DUMPMACHINE\n'+target.stderr,encoding='utf-8')
        if target.returncode or target.stderr.strip():raise ValueError('Compiler target query failed')
        compiler_target,compiler_target_arch=compiler_target_architecture(target.stdout)
        if compiler_target_arch!=expected_arch:raise ValueError('Compiler target differs from native runner architecture')
        binary=directory/'fp-conformance'
        command=[executable,*BASE_C_FLAGS,*flags,
                 str(root/'src/fp-conformance.c'),str(root/'src/fp.c'),'-o',str(binary)]
        (directory/'compile-command.json').write_text(json.dumps(command)+'\n',encoding='utf-8')
        begin=time.monotonic()
        remaining=deadline-time.monotonic()
        if remaining<=0:
            row=dict(schema='public-qfp-native-profile-v1',profile=name,passed=False,stage='overall_timeout',exit_code=124,
                expected_arch=expected_arch,c_flags=BASE_C_FLAGS+flags,compiler_target=compiler_target,compiler_target_arch=compiler_target_arch,elf=None)
            results.append(row);emit(row)
            continue
        build=child_run(command,min(120,remaining),env)
        (directory/'compile.stdout').write_text(build.stdout,encoding='utf-8')
        (directory/'compile.stderr').write_text(build.stderr,encoding='utf-8')
        row=dict(schema='public-qfp-native-profile-v1',profile=name,compiler=compiler,
                 compiler_version_sha256=hashlib.sha256(version.stdout.encode()).hexdigest(),
                 compile_exit=build.returncode,compile_stdout=channel_record(build.stdout),
                 compile_stderr=channel_record(build.stderr),expected_arch=expected_arch,
                 c_flags=BASE_C_FLAGS+flags,compiler_target=compiler_target,compiler_target_arch=compiler_target_arch,elf=None)
        if build.returncode:row.update(passed=False,stage='compile')
        elif deadline-time.monotonic()<=0:row.update(passed=False,stage='overall_timeout',run_exit=124)
        else:
            with binary.open('rb') as stream:row['elf']=elf_metadata(stream.read(64),expected_arch)
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
        runtime_metadata=runtime,
        passed=len(results)==4 and all(r['passed'] for r in results),results=results,
        raw_output_logged=False,arbitrary_channel_text_logged=False,artifacts_uploaded=False,caches_used=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    emit({key:summary[key] for key in ('schema','manifest_sha256','expected_requests_per_profile','profiles','passed','runtime_metadata')})
    return 0 if summary['passed'] else 1

if __name__=='__main__':
    try:code=main()
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        emit(dict(schema='public-qfp-native-run-v1',passed=False,stage='preflight_or_io',reason_code='VALIDATION_FAILED'))
        code=1
    raise SystemExit(code)
