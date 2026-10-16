"""Source extraction, remote-only C17 build/run, and strict result packing.

No package installation, external build dependency, or C execution is allowed
outside a standard public GitHub-hosted manual native Linux job.
"""
import hashlib
import json
import os
import platform
import shutil
import stat
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = 'pbisogno/box3d-quantum-fp-conformance'
PROFILES = ('gcc-o0', 'gcc-o2', 'clang-o2', 'gcc-ubsan')
PER_PROFILE = {'compile.stdout', 'compile.stderr', 'compile.json', 'compiler.txt',
               'run.stdout', 'run.stderr', 'run.json', 'states.jsonl', 'metrics.json'}
FLAGS = {'gcc-o0': ['-O0'], 'gcc-o2': ['-O2'], 'clang-o2': ['-O2'],
         'gcc-ubsan': ['-O1', '-g', '-fsanitize=undefined', '-fno-sanitize-recover=all']}
WORKSPACE = Path(__file__).resolve().parent.parent
META = WORKSPACE / 'protected/physics-metadata.json'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

def metadata():
    m = json.loads(META.read_text())
    assert m['schema'] == 'bfp-physics-payload-v1'
    return m

def source_name(name):
    p = Path(name)
    if '\\' in name or '..' in p.parts or p.is_absolute() or ':' in name:
        return False
    return name == 'engine/LICENSE' or (
        p.suffix in ('.c', '.h', '.inl') and
        (name.startswith('engine/src/') or name.startswith('engine/include/') or
         name.startswith('kernel/') or name.startswith('derived/') or name.startswith('harness/'))
    ) or name == 'harness/criteria.json'

def extract(zip_path, dest):
    m = metadata()
    assert not dest.exists() and not dest.is_symlink()
    raw = zip_path.read_bytes()
    assert len(raw) == m['zip_bytes'] and digest(raw) == m['zip_sha256']
    with zipfile.ZipFile(zip_path) as z:
        entries = z.infolist()
        names = [i.filename for i in entries]
        assert len(names) == len(set(names)) and 'manifest.json' in names
        manifest_data = z.read('manifest.json')
        assert digest(manifest_data) == m['manifest_sha256']
        manifest = json.loads(manifest_data)
        assert manifest['schema'] == 'bfp-physics-source-manifest-v1'
        files = {r['path']: r for r in manifest['files']}
        assert len(files) == len(manifest['files'])
        assert set(names) == set(files) | {'manifest.json'}
        assert 80 <= len(names) <= 200
        contents = {}
        total = 0
        for entry in entries:
            name = entry.filename
            assert name == 'manifest.json' or source_name(name) or (
                name.startswith('luts/') and Path(name).name in
                ('FPSqrt.bytes', 'FPSinCos.bytes', 'FPAcos.bytes', 'FPAsin.bytes', 'FPAtan.bytes'))
            assert not entry.is_dir() and stat.S_ISREG(entry.external_attr >> 16)
            assert entry.file_size <= 16 * 1024 * 1024
            total += entry.file_size
            assert total <= 64 * 1024 * 1024
            data = z.read(entry)
            if name != 'manifest.json':
                r = files[name]
                assert len(data) == r['bytes'] and digest(data) == r['sha256']
            contents[name] = data
    dest.mkdir()
    for name, data in contents.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f:
            f.write(data)

def approved():
    e = os.environ
    arch = e.get('BFP_EXPECTED_ARCH')
    assert arch in ('x64', 'arm64') and platform.system() == 'Linux'
    assert platform.machine().lower() in (('x86_64', 'amd64') if arch == 'x64' else ('aarch64', 'arm64'))
    assert e.get('RUNNER_ARCH') == ('X64' if arch == 'x64' else 'ARM64')
    assert e.get('RUNNER_ENVIRONMENT') == 'github-hosted' and e.get('GITHUB_ACTIONS') == 'true'
    assert e.get('GITHUB_REPOSITORY') == REPO and e.get('GITHUB_REF') == 'refs/heads/main'
    assert e.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    event = json.loads(Path(e['GITHUB_EVENT_PATH']).read_text())
    assert event['repository']['full_name'] == REPO and event['repository']['private'] is False
    assert event['repository']['visibility'] == 'public' and event['repository']['default_branch'] == 'main'
    assert sys.byteorder == 'little' and struct.calcsize('P') == 8
    assert all(shutil.which(p) for p in ('gcc', 'clang', 'python3', 'node'))
    return arch

def run_native():
    arch = approved()
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    assert temp != WORKSPACE and WORKSPACE not in temp.parents
    payload = temp / 'bfp-physics-payload'
    build = temp / 'bfp-physics-build'
    native = temp / 'bfp-physics-native'
    assert not build.exists() and not native.exists()
    build.mkdir(); native.mkdir()
    home = temp / 'bfp-physics-home'; scratch = temp / 'bfp-physics-scratch'
    home.mkdir(); scratch.mkdir()
    env = dict(PATH=os.environ['PATH'], HOME=str(home), TMPDIR=str(scratch),
               LANG='C.UTF-8', LC_ALL='C.UTF-8', PYTHONDONTWRITEBYTECODE='1')
    manifest = json.loads((payload / 'manifest.json').read_text())
    assert manifest['mode'] == 'physics'
    assert digest((payload / 'manifest.json').read_bytes()) == metadata()['manifest_sha256']
    # Recheck every input immediately before compilation.
    for r in manifest['files']:
        path = payload / r['path']
        assert path.is_file() and not path.is_symlink()
        data = path.read_bytes()
        assert len(data) == r['bytes'] and digest(data) == r['sha256']
    sources = sorted((payload / 'engine/src').glob('*.c'))
    assert len(sources) >= 45
    sources += [payload / 'kernel/fp.c', payload / 'harness/test_physics.c']
    summary = dict(schema='bfp-physics-run-v1', manifest_sha256=metadata()['manifest_sha256'],
                   architecture=arch, machine=platform.machine(), os=platform.system(),
                   kernel=platform.release(), runner_environment='github-hosted',
                   pointer_bits=64, byteorder='little', profiles=[], passed=False,
                   native_source_count=len(sources), source_commit=os.environ['GITHUB_SHA'],
                   installations=0, emulation=False, diagnostics_plaintext_logged=False)
    try:
        for name in PROFILES:
            out = build / name; out.mkdir()
            binary = native / name
            compiler = shutil.which('clang' if name == 'clang-o2' else 'gcc')
            version = subprocess.run([compiler, '--version'], env=env, capture_output=True, timeout=10, check=True)
            target = subprocess.run([compiler, '-dumpmachine'], env=env, capture_output=True, timeout=10, check=True).stdout.decode().strip()
            assert target.split('-')[0] in (('x86_64',) if arch == 'x64' else ('aarch64', 'arm64'))
            (out / 'compiler.txt').write_bytes(version.stdout + b'\nTARGET\n' + target.encode() + b'\n')
            command = [compiler, '-std=c17', '-pedantic-errors', '-Wall', '-Wextra',
                       '-DBOX3D_DISABLE_SIMD', '-DBOX3D_DISABLE_AVX2', '-DBOX3D_VALIDATE',
                       '-DB3_ENABLE_ASSERT', *FLAGS[name]]
            for folder in ('engine/include', 'engine/src', 'kernel', 'derived'):
                command += ['-I', str(payload / folder)]
            command += [str(p) for p in sources] + ['-o', str(binary), '-pthread', '-lm']
            started = time.monotonic()
            with (out / 'compile.stdout').open('xb') as stdout, (out / 'compile.stderr').open('xb') as stderr:
                compile_run = subprocess.run(command, env=env, cwd=payload, stdout=stdout, stderr=stderr, timeout=150)
            record = dict(profile=name, compiler_target=target, compile_exit=compile_run.returncode,
                          elapsed_compile_seconds=time.monotonic() - started, passed=False,
                          compiler_version_sha256=digest(version.stdout), flags=command[1:command.index('-I')])
            write_json(out / 'compile.json', dict(command=command, **record))
            if compile_run.returncode == 0:
                raw = binary.read_bytes()
                assert raw[:6] == b'\x7fELF\x02\x01'
                machine = int.from_bytes(raw[18:20], 'little')
                assert machine == (62 if arch == 'x64' else 183)
                record.update(elf_machine=machine, binary_sha256=digest(raw))
                args = [str(binary), '--lut-dir', str(payload / 'luts'), '--output', str(out)]
                with (out / 'run.stdout').open('xb') as stdout, (out / 'run.stderr').open('xb') as stderr:
                    native_run = subprocess.run(args, env=env, cwd=payload, stdout=stdout, stderr=stderr, timeout=90)
                record['run_exit'] = native_run.returncode
                if (out / 'metrics.json').is_file():
                    metrics = json.loads((out / 'metrics.json').read_text())
                    record['metrics_passed'] = metrics.get('passed') is True
                    record['metrics_sha256'] = digest((out / 'metrics.json').read_bytes())
                if (out / 'states.jsonl').is_file():
                    record['states_sha256'] = digest((out / 'states.jsonl').read_bytes())
                record['passed'] = native_run.returncode == 0 and record.get('metrics_passed') is True and 'states_sha256' in record
                write_json(out / 'run.json', record)
            summary['profiles'].append(record)
            print(json.dumps(dict(schema='bfp-physics-profile-v1', arch=arch, profile=name,
                                  compile_exit=record['compile_exit'], run_exit=record.get('run_exit'),
                                  passed=record['passed'], manifest_sha256=summary['manifest_sha256'])), flush=True)
    finally:
        summary['passed'] = len(summary['profiles']) == 4 and all(r['passed'] for r in summary['profiles'])
        write_json(build / 'summary.json', summary)
    return 0 if summary['passed'] else 1

def preprocess():
    arch = approved()
    assert arch == 'x64'
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    payload = temp / 'bfp-physics-payload'
    manifest = json.loads((payload / 'manifest.json').read_text())
    assert manifest['mode'] == 'preprocess' and manifest['source_pin'] == '5d83df83ab47172c2c745b44315e7538ead02397'
    assert digest((payload / 'manifest.json').read_bytes()) == metadata()['manifest_sha256']
    for row in manifest['files']:
        data = (payload / row['path']).read_bytes()
        assert len(data) == row['bytes'] and digest(data) == row['sha256']
    build = temp / 'bfp-physics-build'; assert not build.exists(); build.mkdir()
    out = build / 'preprocess'; out.mkdir()
    env = dict(PATH=os.environ['PATH'], LANG='C.UTF-8', LC_ALL='C.UTF-8')
    source = payload / 'engine/src'
    units = sorted(source.glob('*.c')) + [source / name for name in (
        'physics_world.h','dynamic_tree.h','recording.h','replay.h','world_snapshot.h',
        'contact_solver_wide.inl','convex_manifold_wide.inl')]
    records = []
    for unit in units:
        command = [shutil.which('gcc'), '-std=c17', '-DBOX3D_DISABLE_SIMD',
                   '-DBOX3D_DISABLE_AVX2', '-DBOX3D_VALIDATE', '-DB3_ENABLE_ASSERT',
                   '-DB3_SIMD_WIDTH=4', '-I', str(payload / 'engine/include'),
                   '-I', str(source), '-x', 'c', '-E', str(unit)]
        dest = out / (unit.name + '.i')
        with dest.open('xb') as stdout, (out / (unit.name + '.stderr')).open('xb') as stderr:
            result = subprocess.run(command, env=env, cwd=payload, stdout=stdout, stderr=stderr, timeout=20)
        records.append(dict(module='src/' + unit.name, exit=result.returncode,
                            output_sha256=digest(dest.read_bytes()), bytes=dest.stat().st_size))
    passed = all(r['exit'] == 0 for r in records)
    write_json(build / 'summary.json', dict(schema='bfp-physics-preprocessing-v1',
               source_pin=manifest['source_pin'], manifest_sha256=metadata()['manifest_sha256'],
               architecture=arch, profiles=[], modules=records, passed=passed,
               native_code_compiled=False, native_code_executed=False, installations=0))
    print(json.dumps(dict(schema='bfp-physics-preprocessing-v1', modules=len(records),
                          passed=passed, compiled=False, native_executed=False)))
    return 0 if passed else 1

def pack(root, target):
    assert root.is_dir() and not root.is_symlink() and not target.exists()
    files = []; total = 0
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir():
            assert path.parent == root and path.name in (*PROFILES, 'preprocess')
            continue
        rel = path.relative_to(root).as_posix()
        assert rel == 'summary.json' or (path.parent.parent == root and path.parent.name in PROFILES and path.name in PER_PROFILE) or (
            path.parent == root / 'preprocess' and path.name.endswith(('.c.i','.h.i','.inl.i','.c.stderr','.h.stderr','.inl.stderr')))
        data = path.read_bytes(); total += len(data)
        assert len(data) <= 32 * 1024 * 1024 and total <= 256 * 1024 * 1024
        files.append((rel, data))
    assert files
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in files:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = (stat.S_IFREG | 0o600) << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    raw = target.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    print(json.dumps(dict(zip_bytes=len(raw), zip_sha256=digest(raw), plaintext_bytes=total,
                          files=[dict(path=n, bytes=len(d), sha256=digest(d)) for n, d in files])))

if __name__ == '__main__':
    try:
        if len(sys.argv) == 4 and sys.argv[1] == 'extract':
            extract(Path(sys.argv[2]), Path(sys.argv[3]))
        elif len(sys.argv) == 4 and sys.argv[1] == 'pack':
            pack(Path(sys.argv[2]), Path(sys.argv[3]))
        elif sys.argv == [sys.argv[0], 'run']:
            raise SystemExit(run_native())
        elif sys.argv == [sys.argv[0], 'preprocess']:
            raise SystemExit(preprocess())
        else:
            raise ValueError('Invalid command')
    except Exception:
        raise SystemExit('Physics runner rejected or failed; inspect encrypted diagnostics.')
