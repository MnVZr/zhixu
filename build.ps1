$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Path work\temp,work\previous-versions,release -Force | Out-Null
$env:TEMP = Join-Path $PSScriptRoot 'work\temp'
$env:TMP = $env:TEMP
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'work\pyinstaller-cache'
python -m PyInstaller --noconfirm --clean --onefile --windowed --name '知序' --paths work\vendor --hidden-import pystray._win32 --icon 'web\zhixu.ico' --version-file version_info.txt --add-data 'web;web' --distpath work\package --workpath work\build app.py
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
Copy-Item -LiteralPath 'work\package\知序.exe' -Destination 'release\知序.exe' -Force
Copy-Item -LiteralPath README.md -Destination 'release\使用说明.md' -Force
python package_release.py
if ($LASTEXITCODE -ne 0) { throw '发布包校验失败' }

python -m PyInstaller --noconfirm --clean --onefile --windowed --name 'Zhixu-1.5.0-Setup' --icon 'web\zhixu.ico' --version-file version_info.txt --add-data 'Zhixu-1.5.0-Windows-x64.zip;.' --distpath work\setup-package --workpath work\setup-build installer.py
if ($LASTEXITCODE -ne 0) { throw '安装程序打包失败' }
Copy-Item -LiteralPath 'work\setup-package\Zhixu-1.5.0-Setup.exe' -Destination 'Zhixu-1.5.0-Setup.exe' -Force
python -c "from pathlib import Path; import hashlib; p=Path('Zhixu-1.5.0-Setup.exe'); f=Path('SHA256SUMS.txt'); f.write_text(f.read_text(encoding='ascii')+hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n',encoding='ascii')"
if ($LASTEXITCODE -ne 0) { throw '安装包校验失败' }
