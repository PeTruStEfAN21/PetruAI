# PetruAI - one-script setup for Windows with an NVIDIA GPU.
#   powershell -ExecutionPolicy Bypass -File infra/setup.ps1            # install everything that is missing
#   powershell -ExecutionPolicy Bypass -File infra/setup.ps1 -DryRun    # only show what would be done
# Options: -IncludeQuality (also the 35B MoE model, 17.7 GB, needs >= 24 GB RAM), -SkipModels, -SkipLlama.
# Safe to run again: every step skips what is already there.
param(
    [switch]$DryRun,
    [switch]$IncludeQuality,
    [switch]$SkipModels,
    [switch]$SkipLlama
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$llamaTag = "b11877"

function Step([string]$message) { Write-Host "`n==> $message" -ForegroundColor Cyan }
function Act([string]$description, [scriptblock]$action) {
    if ($DryRun) { Write-Host "[dry-run] $description" -ForegroundColor Yellow }
    else { Write-Host "$description"; & $action }
}
function Fail([string]$message) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 1 }
function Test-Native([string]$commandLine) {
    # Windows PowerShell 5.1 turns redirected native stderr into a terminating error under
    # $ErrorActionPreference = "Stop"; running the probe inside cmd keeps PowerShell out of it.
    & cmd /c "$commandLine >nul 2>&1"
    return ($LASTEXITCODE -eq 0)
}

# 1. Hardware ---------------------------------------------------------------------------------------
Step "Hardware"
$gpuLine = $null
try { $gpuLine = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1) } catch { }
if (-not $gpuLine) { Fail "No NVIDIA GPU found (nvidia-smi failed). Install the NVIDIA driver first." }
$parts = $gpuLine.Split(",")
$gpuName = $parts[0].Trim()
$vramGB = [math]::Round([double]$parts[1].Trim() / 1024, 1)
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Write-Host "GPU: $gpuName, $vramGB GB VRAM; RAM: $ramGB GB"

# 2. Python 3.14 and uv -------------------------------------------------------------------------------
Step "Python 3.14 and uv"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { Fail "Python launcher 'py' missing. Install Python 3.14: winget install Python.Python.3.14" }
if (-not (Test-Native "py -3.14 --version")) { Fail "Python 3.14 missing. Install it: winget install Python.Python.3.14" }
Write-Host "Python 3.14 found."
if (Test-Native "py -3.14 -m uv --version") { Write-Host "uv found." }
else { Act "Install uv (py -3.14 -m pip install uv)" { & py -3.14 -m pip install uv } }

# 3. Agent environment ----------------------------------------------------------------------------------
Step "Agent environment"
Act "uv sync in $repo" { Push-Location $repo; try { & py -3.14 -m uv sync } finally { Pop-Location } }

# 4. llama.cpp CUDA binaries ------------------------------------------------------------------------------
Step "llama.cpp $llamaTag (CUDA 12)"
$bin = Join-Path $repo "infra\llama.cpp\bin"
if (Test-Path (Join-Path $bin "llama-server.exe")) {
    Write-Host "llama-server.exe already installed in $bin"
} elseif ($SkipLlama) {
    Write-Host "Skipped (-SkipLlama)."
} else {
    $release = Invoke-RestMethod "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$llamaTag"
    $assets = @($release.assets | Where-Object { $_.name -match "win-cuda-12.*x64\.zip$" })
    if ($assets.Count -eq 0) { Fail "No CUDA 12 Windows assets found in llama.cpp release $llamaTag." }
    foreach ($asset in $assets) {
        Act "Download and unpack $($asset.name) ($([math]::Round($asset.size / 1MB)) MB)" {
            New-Item -ItemType Directory -Force -Path $bin | Out-Null
            $zip = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest $asset.browser_download_url -OutFile $zip
            Expand-Archive $zip -DestinationPath $bin -Force
            Remove-Item $zip
        }
    }
}

# 5. Models sized to the hardware ----------------------------------------------------------------------------
Step "Models"
$modelArgs = @()
if ($vramGB -ge 5.5) { $modelArgs += "-IncludeMedium" }
if ($IncludeQuality) {
    if ($ramGB -ge 24) { $modelArgs += "-IncludeAll" } else { Write-Host "Quality model skipped: it needs >= 24 GB RAM ($ramGB GB found)." }
}
if ($SkipModels) {
    Write-Host "Skipped (-SkipModels)."
} else {
    Act "infra/setup-models.ps1 $($modelArgs -join ' ')" { & (Join-Path $PSScriptRoot "setup-models.ps1") @modelArgs }
}
if ($vramGB -lt 5.5) {
    $config = Join-Path $env:USERPROFILE ".petru\config.toml"
    Act "Write default_tier = fast to $config (less than 6 GB VRAM)" {
        New-Item -ItemType Directory -Force -Path (Split-Path $config) | Out-Null
        if (-not (Test-Path $config)) { Set-Content -Encoding utf8 $config "[server]`ndefault_tier = `"fast`"" }
    }
}

# 6. The petru command ------------------------------------------------------------------------------------------
Step "petru command on PATH"
Act "uv tool install --editable $repo" {
    & py -3.14 -m uv tool install --editable $repo --force
    & py -3.14 -m uv tool update-shell
}

# 7. Check ---------------------------------------------------------------------------------------------------------
Step "petru doctor"
Act "petru doctor" { Push-Location $repo; try { & py -3.14 -m uv run petru doctor } finally { Pop-Location } }
Write-Host "`nDone. Open a new terminal and run: petru" -ForegroundColor Green
