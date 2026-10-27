# Antrenare continuă, până la oprire: profesorul 35B generează traiectorii verificate pe sarcinile Exercism
# validate (-TeachHours), apoi generalistul se antrenează pe ele (build, train, export, eval, promote prin
# run_night.ps1, fără pașii trajectories și specialists), apoi iar, la nesfârșit.
#   powershell -NoProfile -ExecutionPolicy Bypass -File training/run_continuous.ps1 -TeachHours 5 -TrainHours 6
# Oprire: Stop-ScheduledTask PetruAI-continuous (sau închiderea procesului); progresul profesorului e global,
# deci o repornire continuă de unde a rămas.
param(
    [double]$TeachHours = 5,
    [double]$TrainHours = 6,
    [int]$Parallel = 3
)
$ErrorActionPreference = "Continue"
$training = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $training
# A task started at logon may carry an old PATH: take it fresh, so every toolchain installed since is found.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$log = Join-Path $training "runs\continuous.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
while ($true) {
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    $until = (Get-Date).AddHours($TeachHours).ToString("s")
    "[$(Get-Date -Format s)] teacher until $until, parallel $Parallel" | Out-File -Append -Encoding utf8 $log
    & py -3.14 -m uv run python -X utf8 -m petru_train.teacher --until $until --parallel $Parallel *>&1 | Out-File -Append -Encoding utf8 $log
    "[$(Get-Date -Format s)] teacher exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
    $run = "c-" + (Get-Date -Format "yyyy-MM-dd-HHmm")
    "[$(Get-Date -Format s)] training run $run" | Out-File -Append -Encoding utf8 $log
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $training "run_night.ps1") -Run $run -Hours $TrainHours -Skip trajectories,specialists
    "[$(Get-Date -Format s)] run $run exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
}
