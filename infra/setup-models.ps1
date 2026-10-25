#!/usr/bin/env pwsh
# PetruAI — Model download script
# Downloads the minimal model set for local agentic coding on RTX 4050 (6 GB VRAM).
# Reluabil: dacă un fișier există deja și e complet, nu-l redescarcă.
#
# Usage:
#   .\setup-models.ps1                  # descarcă modelul mic (Qwen3.5-4B) + embeddings
#   .\setup-models.ps1 -IncludeMedium   # + Qwen3.5-9B
#   .\setup-models.ps1 -IncludeAll      # + Qwen3.6-35B-A3B (17.7 GB!)

param(
    [switch]$IncludeMedium,
    [switch]$IncludeAll
)

$ErrorActionPreference = "Stop"
$modelsDir = Join-Path $PSScriptRoot "llama.cpp\models"

if (-not (Test-Path $modelsDir)) {
    New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
}

# Use python -m huggingface_hub as the CLI
function Download-Model {
    param(
        [string]$RepoId,
        [string]$Filename,
        [string]$Label
    )
    $targetPath = Join-Path $modelsDir $Filename
    if (Test-Path $targetPath) {
        Write-Host "[SKIP] $Label already exists: $targetPath" -ForegroundColor Green
        return
    }
    Write-Host "[DOWNLOAD] $Label from $RepoId ..." -ForegroundColor Cyan
    python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='$RepoId', filename='$Filename', local_dir=r'$modelsDir')"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to download $Label"
        exit 1
    }
    Write-Host "[OK] $Label saved to $targetPath" -ForegroundColor Green
}

# ─── 1. Embeddings model (tiny, always download) ─────────────────────────
Download-Model `
    -RepoId "ggml-org/embeddinggemma-2-GGUF" `
    -Filename "embeddinggemma-2-Q8_0.gguf" `
    -Label "EmbeddingGemma 2 (embeddings, ~290 MB)"

# ─── 2. Qwen3.5-4B (small coding model, ~2.5 GB) ────────────────────────
Download-Model `
    -RepoId "mradermacher/Qwen3.5-4B-GGUF" `
    -Filename "Qwen3.5-4B.IQ4_XS.gguf" `
    -Label "Qwen3.5-4B IQ4_XS (small coder, ~2.53 GB)"

# ─── 3. Qwen3.5-9B (medium coding model, ~5.2 GB) ───────────────────────
if ($IncludeMedium -or $IncludeAll) {
    Download-Model `
        -RepoId "mradermacher/Qwen3.5-9B-GGUF" `
        -Filename "Qwen3.5-9B.IQ4_XS.gguf" `
        -Label "Qwen3.5-9B IQ4_XS (medium coder, ~5.17 GB)"
}

# ─── 4. Qwen3.6-35B-A3B (quality MoE model, ~17.7 GB) ───────────────────
if ($IncludeAll) {
    Download-Model `
        -RepoId "unsloth/Qwen3.6-35B-A3B-GGUF" `
        -Filename "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf" `
        -Label "Qwen3.6-35B-A3B UD-IQ4_XS (quality coder, ~17.7 GB)"
}

Write-Host ""
Write-Host "=== Done! Models in $modelsDir ===" -ForegroundColor Green
Get-ChildItem $modelsDir -Filter "*.gguf" | ForEach-Object {
    Write-Host "  $($_.Name)  ($([math]::Round($_.Length/1GB,2)) GB)"
}
