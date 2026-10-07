# Rebuilds dist\DicteeLocale and relaunches it, keeping the exe's own
# config.json (language, microphone, padlock...) and dictation.log.
# PyInstaller wipes the output folder on every build.

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
$dist = "dist\DicteeLocale"
$keep = Join-Path $env:TEMP "DicteeLocale-keep"
try {
    Stop-Process -Name DicteeLocale -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
    New-Item -ItemType Directory -Force $keep | Out-Null
    foreach ($f in "config.json", "dictation.log") {
        if (Test-Path "$dist\$f") { Copy-Item "$dist\$f" $keep -Force }
    }

    $ErrorActionPreference = "Continue"  # PyInstaller logs INFO lines to stderr
    & .venv\Scripts\pyinstaller --noconfirm --noconsole --onedir `
        --name DicteeLocale --icon app.ico `
        --collect-all faster_whisper --collect-all ctranslate2 `
        --collect-all onnxruntime `
        --add-data ".venv\Lib\site-packages\nvidia;nvidia" `
        --add-data "sons/coller.wav;sons" --add-data "sons/envoyer.wav;sons" `
        --add-data "sons/colibri.wav;sons" main.py
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
} finally {
    # Put the exe's own files back, even after a failed build, then delete
    # the copy: logs from old versions may still hold dictated text.
    New-Item -ItemType Directory -Force $dist | Out-Null
    foreach ($f in "config.json", "dictation.log") {
        if (Test-Path "$keep\$f") { Copy-Item "$keep\$f" $dist -Force }
    }
    if (-not (Test-Path "$dist\config.json")) { Copy-Item config.json $dist -Force }
    Remove-Item $keep -Recurse -Force -ErrorAction SilentlyContinue
    Pop-Location
}
Start-Process "$PSScriptRoot\$dist\DicteeLocale.exe"
Write-Host "Built and relaunched $dist\DicteeLocale.exe"
