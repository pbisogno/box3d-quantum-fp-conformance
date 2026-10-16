"""Pack only known result files. No source, LUT, request, executable, or secret."""
import argparse,hashlib,json,os,stat,zipfile
from pathlib import Path
PROFILES=('gcc-o0','gcc-o2','clang-o2','gcc-ubsan')
NAMES={'compile.stdout','compile.stderr','compiler-version.stdout','compiler-version.stderr','compile-command.json','run.stdout','run.stderr','actual.jsonl','comparison.json'}
CAP=8*1024*1024
def pack(root,out):
    root=Path(root);files=[];total=0
    if root.is_symlink()or not root.is_dir():raise ValueError('Invalid build root')
    for p in root.rglob('*'):
        if p.is_symlink():raise ValueError('Result link rejected')
        if p.is_dir():
            if p.parent!=root or p.name not in PROFILES:raise ValueError('Unknown result directory')
            continue
        if not p.is_file():raise ValueError('Unknown result entry')
        rel=p.relative_to(root).as_posix()
        if p.name=='fp-conformance'and p.parent.name in PROFILES and p.parent.parent==root:continue
        if rel!='summary.json'and not(p.parent.parent==root and p.parent.name in PROFILES and p.name in NAMES):raise ValueError('Unknown result file')
        size=p.stat().st_size;total+=size
        if size>64*1024*1024 or total>256*1024*1024:raise ValueError('Result plaintext size cap exceeded')
        files.append((rel,p,size))
    if not files:raise ValueError('Empty result archive')
    records=[]
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for rel,p,size in sorted(files):
            raw=p.read_bytes()
            if len(raw)!=size:raise ValueError('Result changed while archiving')
            zi=zipfile.ZipInfo(rel,date_time=(1980,1,1,0,0,0));zi.create_system=3;zi.external_attr=(stat.S_IFREG|0o600)<<16;zi.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(zi,raw,compresslevel=9);records.append({'path':rel,'bytes':size,'sha256':hashlib.sha256(raw).hexdigest()})
    if Path(out).stat().st_size>CAP:raise ValueError('Compressed result archive exceeds eight MiB; no truncation')
    raw=Path(out).read_bytes()
    return dict(files=records,zip_bytes=len(raw),zip_sha256=hashlib.sha256(raw).hexdigest(),plaintext_bytes=total)
def main():
    a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--output',required=True);v=a.parse_args()
    result=pack(v.input,v.output);print(json.dumps(result))
if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Result packing rejected')
