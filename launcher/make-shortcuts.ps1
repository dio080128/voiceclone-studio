param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [switch]$Desktop
)

# 快捷方式创建：任何异常都吞掉，绝不阻断安装
$ErrorActionPreference = 'SilentlyContinue'

$name = '声纹工坊'
$exe = Join-Path $AppDir ($name + '.exe')
if (-not (Test-Path $exe)) {
    $exe = Get-ChildItem -Path $AppDir -Filter '*.exe' | Select-Object -First 1 -ExpandProperty FullName
}
if (-not (Test-Path $exe)) { return }

$shell = New-Object -ComObject WScript.Shell

function New-Shortcut([string]$linkPath) {
    if (-not $linkPath) { return }
    $lnk = $shell.CreateShortcut($linkPath)
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $AppDir
    $lnk.IconLocation = ($exe + ',0')
    $lnk.Description = '声纹工坊 · 本地 AI 声音克隆'
    $lnk.Save()
}

if ($Desktop) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ($desktop) { New-Shortcut (Join-Path $desktop ($name + '.lnk')) }
}
else {
    $programs = [Environment]::GetFolderPath('Programs')
    if ($programs) { New-Shortcut (Join-Path $programs ($name + '.lnk')) }
}
