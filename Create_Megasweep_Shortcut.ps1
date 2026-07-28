param(
    [string]$AppRoot = $PSScriptRoot,
    [switch]$Desktop
)

$ErrorActionPreference = "Stop"

$resolvedRoot = [System.IO.Path]::GetFullPath($AppRoot).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$pythonwPath = Join-Path $resolvedRoot ".venv\Scripts\pythonw.exe"
$entryPath = Join-Path $resolvedRoot "main.py"
$iconPath = Join-Path $resolvedRoot "assets\megasweep.ico"

foreach ($requiredPath in @($pythonwPath, $entryPath, $iconPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file not found: $requiredPath"
    }
}

$shortcutDirectory = $resolvedRoot
if ($Desktop) {
    $shortcutDirectory = [Environment]::GetFolderPath("Desktop")
}
$shortcutPath = Join-Path $shortcutDirectory "Megasweep Analysis.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonwPath
$shortcut.Arguments = "`"$entryPath`""
$shortcut.WorkingDirectory = $resolvedRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Launch Megasweep PL and reflection analysis"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Output "Created shortcut: $shortcutPath"
