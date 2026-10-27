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
function Count-Trajectories {
    $file = Join-Path $training "data	rajectories-exercism.jsonl"
    if (Test-Path $file) { return ([System.IO.File]::ReadLines($file) | Measure-Object).Count }
    return 0
}
while ($true) {
    $before = Count-Trajectories
    $until = (Get-Date).AddHours($TeachHours).ToString("s")
    "[$(Get-Date -Format s)] teacher until $until, parallel $Parallel" | Out-File -Append -Encoding utf8 $log
    & py -3.14 -m uv run python -X utf8 -m petru_train.teacher --until $until --parallel $Parallel *>&1 | Out-File -Append -Encoding utf8 $log
    $teach = $LASTEXITCODE
    $new = (Count-Trajectories) - $before
    "[$(Get-Date -Format s)] teacher exit=$teach, $new new trajectories" | Out-File -Append -Encoding utf8 $log
    if ($new -le 0) {
        # Training again on the same data only buys another noisy chance at the gate: wait for new data.
        $wait = if ($teach -eq 3) { 3600 } else { 600 }
        "[$(Get-Date -Format s)] no new trajectories: no training; next try in $wait s" | Out-File -Append -Encoding utf8 $log
        Start-Sleep -Seconds $wait
        continue
    }
    $run = "c-" + (Get-Date -Format "yyyy-MM-dd-HHmm")
    "[$(Get-Date -Format s)] training run $run" | Out-File -Append -Encoding utf8 $log
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $training "run_night.ps1") -Run $run -Hours $TrainHours -Skip trajectories,specialists
    "[$(Get-Date -Format s)] run $run exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
}
