param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$BuildRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SpecPath = Join-Path $BuildRoot "hanse_pygame.spec"
$DistPath = Join-Path $BuildRoot "dist\\windows"
$WorkPath = Join-Path $BuildRoot ".pyinstaller\\windows"

New-Item -ItemType Directory -Force -Path $DistPath | Out-Null
New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null

& $PythonExe -m PyInstaller --noconfirm --clean --distpath $DistPath --workpath $WorkPath $SpecPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Windows build complete."
Write-Host "Executable: $DistPath\\Hanse_Atheria\\Hanse_Atheria.exe"
