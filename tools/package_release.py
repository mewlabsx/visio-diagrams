"""Create reproducible skill and example ZIPs from this standalone repository."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and p.suffix != '.pyc')


def archive(path, entries):
    if path.exists():
        raise FileExistsError('Refusing to overwrite: ' + str(path))
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, source in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026,10,10,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, source.read_bytes())
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP integrity check failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root=args.root.resolve(); out=args.out.resolve()
    version=re.search(r'version:\s*"([^"]+)"', (root/'SKILL.md').read_text(encoding='utf-8')).group(1)
    selected=[]
    for name in ('SKILL.md','README.md','RELEASE_NOTES.md'):
        selected.append((name,root/name))
    for folder in ('scripts','references','assets','agents'):
        selected.extend((p.relative_to(root).as_posix(),p) for p in files(root/folder))
    out.mkdir(parents=True,exist_ok=True)
    manifest={'name':'visio-diagrams','version':version,'files':[
        {'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for name,p in sorted(selected)]}
    manifest_path=out/f'visio-diagrams-v{version}.manifest.json'
    if manifest_path.exists():raise FileExistsError(str(manifest_path))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    packages=[out/f'visio-diagrams-v{version}.zip']
    archive(packages[0],[('visio-diagrams/'+name,p) for name,p in selected])
    examples=root/'examples'
    if examples.is_dir():
        packages.append(out/f'visio-diagrams-v{version}-examples.zip')
        archive(packages[-1],[('examples/'+p.relative_to(examples).as_posix(),p) for p in files(examples)])
    checksum=out/'SHA256SUMS.txt'
    if checksum.exists():raise FileExistsError(str(checksum))
    checksum.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
                               for p in [*packages,manifest_path]),encoding='ascii')
    print(json.dumps({'version':version,'files':len(selected),'packages':[p.name for p in packages]},indent=2))


if __name__=='__main__':
    main()
