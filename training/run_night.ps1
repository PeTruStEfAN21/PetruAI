# O noapte de antrenare: oprește orice llama-server (eliberează VRAM), rulează orchestratorul, loghează.
#   powershell -NoProfile -ExecutionPolicy Bypass -File training/run_night.ps1 -Run 2026-10-27 -Hours 7
# Reluare după o întrerupere: aceeași comandă, același -Run (pașii terminați sunt săriți).
param(
    [Parameter(Mandatory = $true)][string]$Run,
    [double]$Hours = 7,
    [switch]$SkipTrajectories
)
$ErrorActionPreference = "Continue"
$training = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $training
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$runDir = Join-Path $training "runs\$Run"
New-Item -ItemType Directory -Force $runDir | Out-Null
$log = Join-Path $runDir "nightly.log"
$args = @("-3.14", "-m", "uv", "run", "python", "-X", "utf8", "-m", "petru_train.nightly", "--run", $Run, "--hours", "$Hours")
if ($SkipTrajectories) { $args += "--skip-trajectories" }
"[$(Get-Date -Format s)] start run=$Run hours=$Hours" | Out-File -Append -Encoding utf8 $log
& py @args 2>&1 | Tee-Object -FilePath $log -Append
"[$(Get-Date -Format s)] exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
exit $LASTEXITCODE
