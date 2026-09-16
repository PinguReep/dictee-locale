# Rebuilds dist\DicteeLocale and relaunches it, keeping the exe's own
# config.json (language, microphone, padlock...) and dictation.log.
# PyInstaller wipes the output folder on every build.

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    $dist = "dist\DicteeLocale"
    $keep = Join-Path $env:TEMP "DicteeLocale-keep"

    Stop-Process -Name DicteeLocale -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
    New-Item -ItemType Directory -Force $keep | Out-Null
    foreach ($f in "config.json", "dictation.log") {
        if (Test-Path "$dist\$f") { Copy-Item "$dist\$f" $keep -Force }
    }

    & .venv\Scripts\pyinstaller --noconfirm --noconsole --onedir `
        --name DicteeLocale --icon app.ico `
        --collect-all faster_whisper --collect-all ctranslate2 `
        --collect-all onnxruntime `
        --add-data ".venv\Lib\site-packages\nvidia;nvidia" `
        --add-data "sons/coller.wav;sons" --add-data "sons/envoyer.wav;sons" `
        --add-data "sons/colibri.wav;sons" main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

    if (Test-Path "$keep\config.json") {
        Copy-Item "$keep\config.json" $dist -Force
    } else {
        Copy-Item config.json $dist -Force
    }
    if (Test-Path "$keep\dictation.log") {
        Copy-Item "$keep\dictation.log" $dist -Force
    }
    Remove-Item $keep -Recurse -Force  # the log copy holds dictated text

    Start-Process "$dist\DicteeLocale.exe"
    Write-Host "Built and relaunched $dist\DicteeLocale.exe"
} finally {
    Pop-Location
}
