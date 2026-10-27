# Specialiștii de limbaj, după (sau fără) o noapte deja pornită: așteaptă să se termine rularea -Run dacă e încă
# activă, apoi antrenează, exportă, evaluează și promovează specialiștii până la -Until.
#   powershell -NoProfile -ExecutionPolicy Bypass -File training/run_specialists.ps1 -Run 2026-10-27 `
#       -Until 2026-10-27T11:15 -Only python,web,flutter
param(
    [Parameter(Mandatory = $true)][string]$Run,
    [Parameter(Mandatory = $true)][string]$Until,
    [string]$Only = ""
)
$ErrorActionPreference = "Continue"
$training = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $training
$runDir = Join-Path $training "runs\$Run"
New-Item -ItemType Directory -Force $runDir | Out-Null
$log = Join-Path $runDir "specialists.log"
$nightLog = Join-Path $runDir "nightly.log"
"[$(Get-Date -Format s)] waiting for the night run to finish" | Out-File -Append -Encoding utf8 $log
while ((Test-Path $nightLog) -and -not (Select-String -Path $nightLog -Pattern "\] exit=" -Quiet)) {
    if ((Get-Date) -ge [datetime]$Until) { "[$(Get-Date -Format s)] deadline reached while waiting" | Out-File -Append -Encoding utf8 $log; exit 0 }
    Start-Sleep -Seconds 60
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$pyArgs = @("-3.14", "-m", "uv", "run", "python", "-X", "utf8", "-m", "petru_train.specialist_night", "--run", $Run, "--until", $Until)
if ($Only) { $pyArgs += @("--only", $Only) }
"[$(Get-Date -Format s)] start specialists run=$Run until=$Until only=$Only" | Out-File -Append -Encoding utf8 $log
& py @pyArgs *>&1 | Out-File -Append -Encoding utf8 $log
"[$(Get-Date -Format s)] exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
exit $LASTEXITCODE
