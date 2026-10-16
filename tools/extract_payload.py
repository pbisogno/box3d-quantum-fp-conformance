"""Validate the entire authenticated ZIP before transactionally creating output."""
import argparse,hashlib,json,os,platform,shutil,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath
MANIFEST='8d7708a1b7aeb04d2c91955d95392b77a8d7dd86762b7a34a8d3ed08efaf59ab'
MAX_TOTAL=32*1024*1024
def unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('Duplicate metadata key')
        out[k]=v
    return out
def read_json(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in()).throw(ValueError('Nonfinite JSON')))
def digest(raw):return hashlib.sha256(raw).hexdigest()
def validate_zip(archive,metadata):
    if metadata.get('schema')!='bfp-encrypted-payload-v1'or metadata.get('manifest_sha256')!=MANIFEST:raise ValueError('Metadata identity mismatch')
    records=metadata['files']
    if type(records)is not list or len(records)!=15:raise ValueError('Expected exactly fifteen files')
    expected={}
    for row in records:
        if set(row)!={'path','bytes','sha256'}or type(row['bytes'])is not int or row['bytes']<0:raise ValueError('Invalid inventory record')
        name=row['path']
        if type(name)is not str or '\\'in name or ':'in name or name.startswith('/')or str(PurePosixPath(name))!=name or any(p in ('','..','.')for p in name.split('/')):raise ValueError('Unsafe archive path')
        if name in expected:raise ValueError('Duplicate inventory path')
        expected[name]=row
    if sum(x['bytes']for x in records)>MAX_TOTAL:raise ValueError('Payload total exceeds bound')
    data={};total=0
    with zipfile.ZipFile(archive)as z:
        infos=z.infolist()
        if len(infos)!=15 or len({x.filename for x in infos})!=15 or {x.filename for x in infos}!=set(expected):raise ValueError('ZIP inventory mismatch')
        for info in infos:
            row=expected[info.filename];mode=(info.external_attr>>16)&0xffff
            if info.is_dir()or info.flag_bits&1 or stat.S_ISLNK(mode)or stat.S_IFMT(mode)not in (0,stat.S_IFREG)or info.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('Unsupported ZIP entry')
            if info.file_size!=row['bytes']or info.file_size>MAX_TOTAL:raise ValueError('ZIP declared size mismatch')
            with z.open(info)as source:raw=source.read(row['bytes']+1)
            total+=len(raw)
            if len(raw)!=row['bytes']or total>MAX_TOTAL or digest(raw)!=row['sha256']:raise ValueError('ZIP entry digest/size mismatch')
            data[info.filename]=raw
    if digest(data.get('manifest.json',b''))!=MANIFEST:raise ValueError('Manifest digest mismatch')
    m=read_json(data['manifest.json']);mf={x['path']:x for x in m['files']}
    if len(mf)!=14 or set(mf)!=(set(data)-{'manifest.json'}):raise ValueError('Manifest inventory mismatch')
    for name,row in mf.items():
        if len(data[name])!=row['bytes']or digest(data[name])!=row['sha256']:raise ValueError('Manifest content mismatch')
    return data
def extract(archive,metadata,out,public_src):
    data=validate_zip(archive,metadata)
    for name in ('fp.h','fp.c','fp-conformance.c','sha256.h'):
        p=public_src/name
        if p.is_symlink()or p.read_bytes()!=data['src/'+name]:raise ValueError('Public C source differs from authenticated payload')
    out=Path(out)
    if out.exists()or out.is_symlink():raise ValueError('Output already exists')
    scratch=Path(tempfile.mkdtemp(prefix='.bfp-extract-',dir=out.parent));os.chmod(scratch,0o700)
    try:
        for name,raw in data.items():
            p=scratch/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);os.chmod(p,0o600)
        scratch.rename(out)
    finally:
        if scratch.exists():shutil.rmtree(scratch)
    return dict(files=len(data),bytes=sum(map(len,data.values())),manifest_sha256=MANIFEST)
def main():
    a=argparse.ArgumentParser();a.add_argument('--zip',required=True);a.add_argument('--metadata',required=True);a.add_argument('--output',required=True);a.add_argument('--public-src',required=True);v=a.parse_args()
    e=os.environ
    if e.get('GITHUB_ACTIONS')!='true'or platform.system()!='Linux'or platform.machine().lower()not in ('x86_64','amd64')or e.get('GITHUB_REPOSITORY_VISIBILITY')!='public'or e.get('GITHUB_REPOSITORY')!='pbisogno/box3d-quantum-fp-conformance'or e.get('GITHUB_REF')!='refs/heads/main'or e.get('GITHUB_EVENT_NAME')!='workflow_dispatch':raise ValueError('Unapproved extraction environment')
    event=read_json(Path(e['GITHUB_EVENT_PATH']).read_bytes());repo=event['repository']
    if repo['full_name']!=e['GITHUB_REPOSITORY']or repo['private']is not False or repo['visibility']!='public'or repo['default_branch']!='main':raise ValueError('Repository event mismatch')
    temp=Path(e['RUNNER_TEMP']).resolve();out=Path(v.output).absolute();workspace=Path(e['GITHUB_WORKSPACE']).resolve()
    if out.parent!=temp or out==workspace or workspace in out.parents or out.exists()or out.is_symlink():raise ValueError('Unsafe output location')
    metadata=read_json(Path(v.metadata).read_bytes());raw=Path(v.zip).read_bytes()
    if len(raw)!=metadata['zip_bytes']or digest(raw)!=metadata['zip_sha256']:raise ValueError('ZIP identity mismatch')
    result=extract(v.zip,metadata,out,Path(v.public_src));print(json.dumps(dict(schema='bfp-payload-restored-v1',**result)))
if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Authenticated payload extraction rejected')
