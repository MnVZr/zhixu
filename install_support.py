"""Per-user installation and desktop shortcuts; personal libraries are never touched."""
from pathlib import Path
import base64
import os
import shutil
import subprocess
import tempfile
import zipfile

def create_shortcut(executable):
    executable=Path(executable).resolve(strict=True)
    if os.name!='nt':raise ValueError('桌面快捷方式仅支持 Windows')
    quoted="'"+str(executable).replace("'","''")+"'"
    code="$ErrorActionPreference='Stop';$s=New-Object -ComObject WScript.Shell;$d=$s.SpecialFolders.Item('Desktop');$p=Join-Path $d '知序.lnk';$l=$s.CreateShortcut($p);$l.TargetPath="+quoted+";$l.WorkingDirectory=[IO.Path]::GetDirectoryName("+quoted+");$l.IconLocation="+quoted+"+',0';$l.Description='知序 · 让生活更有序';$l.Save();[Console]::OutputEncoding=[Text.Encoding]::UTF8;Write-Output $p"
    encoded=base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=30)
    if result.returncode:raise ValueError('无法创建快捷方式，请检查桌面是否可写')
    path=Path(result.stdout.decode('utf-8-sig').strip())
    if not path.is_file():raise ValueError('快捷方式创建失败')
    return path

def install_package(archive,target,shortcut=True):
    target=Path(target).expanduser()
    if not target.is_absolute():raise ValueError('请选择绝对安装路径')
    target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if '知序.exe' not in z.namelist():raise ValueError('安装包缺少程序')
        for item in z.infolist():
            parts=item.filename.replace('\\','/').split('/')
            if item.filename.startswith(('/','\\')) or ':' in item.filename or '..' in parts or any(p.lower() in ('data','attachments','upgrade-backups') for p in parts):raise ValueError('无效安装包路径')
        # Write only packaged program/document files. Existing data folders stay intact.
        with tempfile.TemporaryDirectory(prefix='zhixu-install-') as temporary:
            staged=Path(temporary);z.extractall(staged)
            files=[p for p in staged.rglob('*') if p.is_file()]
            files.sort(key=lambda p:p.name=='知序.exe')
            for file in files:
                destination=target/file.relative_to(staged);destination.parent.mkdir(parents=True,exist_ok=True)
                fd,tempname=tempfile.mkstemp(prefix='.zhixu-',dir=destination.parent);os.close(fd)
                pending=Path(tempname)
                try:shutil.copy2(file,pending);os.replace(pending,destination)
                finally:pending.unlink(missing_ok=True)
    executable=target/'知序.exe'
    if shortcut:create_shortcut(executable)
    return executable
