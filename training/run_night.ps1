# O noapte de antrenare: oprește orice llama-server (eliberează VRAM), rulează orchestratorul, loghează.
#   powershell -NoProfile -ExecutionPolicy Bypass -File training/run_night.ps1 -Run 2026-10-27 -Hours 7
# Reluare după o întrerupere: aceeași comandă, același -Run (pașii terminați sunt săriți).
# -Skip build,trajectories,... marchează pași ca făcuți fără să-i ruleze (util pentru teste).
param(
    [Parameter(Mandatory = $true)][string]$Run,
    [double]$Hours = 7,
    [switch]$SkipTrajectories,
    [string[]]$Skip = @()
)
$ErrorActionPreference = "Continue"
$training = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $training
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$runDir = Join-Path $training "runs\$Run"
New-Item -ItemType Directory -Force $runDir | Out-Null
$log = Join-Path $runDir "nightly.log"
$pyArgs = @("-3.14", "-m", "uv", "run", "python", "-X", "utf8", "-m", "petru_train.nightly", "--run", $Run, "--hours", "$Hours")
if ($SkipTrajectories) { $pyArgs += "--skip-trajectories" }
$steps = @($Skip | ForEach-Object { $_ -split "," } | Where-Object { $_ })
if ($steps.Count -gt 0) { $pyArgs += "--skip"; $pyArgs += $steps }
"[$(Get-Date -Format s)] start run=$Run hours=$Hours skip=$($steps -join ',')" | Out-File -Append -Encoding utf8 $log
& py @pyArgs *>&1 | Out-File -Append -Encoding utf8 $log
$code = $LASTEXITCODE
"[$(Get-Date -Format s)] exit=$code" | Out-File -Append -Encoding utf8 $log
exit $code
