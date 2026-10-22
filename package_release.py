"""Allowlist-only release packaging: never traverse the user's release/data folder."""
from pathlib import Path
import hashlib
import zipfile
ROOT=Path(__file__).parent
def main():
    output=ROOT/'Zhixu-1.5.0-Windows-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT/'release/知序.exe','知序.exe')
        for name in ('README.md','LICENSE','CHANGELOG.md','THIRD_PARTY.md'):z.write(ROOT/name,name)
        for folder in ('third_party','docs'):
            for file in (ROOT/folder).rglob('*'):
                if file.is_file():z.write(file,file.relative_to(ROOT).as_posix())
        assert not any(n.endswith(('.db','.pyc')) or '/data/' in n or '/attachments/' in n for n in z.namelist())
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    (ROOT/'SHA256SUMS.txt').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(output.name,round(output.stat().st_size/1024**2,1),'MB')
if __name__=='__main__':main()
