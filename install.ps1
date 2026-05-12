param([switch]$Force)

$ErrorActionPreference = "Stop"

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Dir ".venv"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$Python = Join-Path $Venv "Scripts\python.exe"
$Hf = Join-Path $Venv "Scripts\hf.exe"

Write-Host "tinytalk installer"
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found. Install it from https://www.python.org/downloads/"
    exit 1
}

if (Test-Path $Venv) {
    if (-not $Force) {
        $answer = Read-Host "existing install found. reinstall? [y/N]"
        if ($answer -notmatch '^[Yy]$') { Write-Host "aborted."; exit 0 }
    }
    Write-Host "removing existing venv..."
    Remove-Item -Recurse -Force $Venv
}

Write-Host "creating venv..."
python -m venv $Venv
& $Pip install --upgrade pip -q
Write-Host ""

Write-Host "Windows found, installing faster-whisper"
& $Pip install faster-whisper windows-curses numpy sounddevice scipy huggingface_hub[cli] tqdm cryptography -q

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Install failed. Check the error above."
    exit 1
}

Write-Host ""
Write-Host "installing tiny model (default)..."
& $Hf download Systran/faster-whisper-tiny --quiet
Write-Host "done."

Write-Host ""
Write-Host "optional models (run these to install more):"
Write-Host "  base   ~141MB   hf download Systran/faster-whisper-base"
Write-Host "  small  ~464MB   hf download Systran/faster-whisper-small"
Write-Host "  medium ~1.5GB   hf download Systran/faster-whisper-medium"
Write-Host "  large  ~3GB     hf download Systran/faster-whisper-large-v3"
Write-Host ""
Write-Host "  browse all: https://huggingface.co/Systran"
Write-Host "  for faster downloads, please log in first: hf auth login"

Write-Host ""
Write-Host "run: & '$Python' tinytalk.py"
