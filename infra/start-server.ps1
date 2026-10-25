#!/usr/bin/env pwsh
# PetruAI — Quick start script for llama-server
# Usage:
#   .\start-server.ps1                    # Qwen3.5-4B (fast, default)
#   .\start-server.ps1 -Model 9b          # Qwen3.5-9B
#   .\start-server.ps1 -Model 35b         # Qwen3.6-35B-A3B (MoE, expert offload)
#   .\start-server.ps1 -Port 8081         # custom port

param(
    [ValidateSet("4b", "9b", "35b")]
    [string]$Model = "4b",
    [int]$Port = 8080,
    [int]$ContextSize = 8192
)

$ErrorActionPreference = "Stop"
$binDir = Join-Path $PSScriptRoot "llama.cpp\bin"
$modelsDir = Join-Path $PSScriptRoot "llama.cpp\models"
$server = Join-Path $binDir "llama-server.exe"

if (-not (Test-Path $server)) {
    Write-Error "llama-server.exe not found at $server. Run setup first."
    exit 1
}

switch ($Model) {
    "4b" {
        $modelFile = Join-Path $modelsDir "Qwen3.5-4B.IQ4_XS.gguf"
        $args = @("-m", $modelFile, "-ngl", "99", "-c", $ContextSize,
                  "--port", $Port, "--flash-attn", "on", "--jinja",
                  "--cache-type-k", "q8_0", "--cache-type-v", "q8_0")
        Write-Host "=== Starting Qwen3.5-4B (fully in VRAM, ~51 tok/s) ===" -ForegroundColor Cyan
    }
    "9b" {
        $modelFile = Join-Path $modelsDir "Qwen3.5-9B.IQ4_XS.gguf"
        $args = @("-m", $modelFile, "-ngl", "99", "-c", $ContextSize,
                  "--port", $Port, "--flash-attn", "on", "--jinja",
                  "--cache-type-k", "q8_0", "--cache-type-v", "q8_0")
        Write-Host "=== Starting Qwen3.5-9B (fully in VRAM, ~32 tok/s) ===" -ForegroundColor Cyan
    }
    "35b" {
        $modelFile = Join-Path $modelsDir "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
        # MoE expert offload: all expert weights on CPU, attention & embeddings on GPU
        $args = @("-m", $modelFile, "-ngl", "99", "--cpu-moe",
                  "-c", $ContextSize, "--port", $Port,
                  "--flash-attn", "on", "--jinja",
                  "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
                  "--cache-prompt")
        Write-Host "=== Starting Qwen3.6-35B-A3B (MoE, expert offload) ===" -ForegroundColor Yellow
    }
}

if (-not (Test-Path $modelFile)) {
    Write-Error "Model not found: $modelFile`nRun: .\setup-models.ps1 to download models."
    exit 1
}

Write-Host "Model: $modelFile"
Write-Host "Port: $Port | Context: $ContextSize"
Write-Host "API: http://127.0.0.1:$Port/v1/chat/completions"
Write-Host "Health: http://127.0.0.1:$Port/health"
Write-Host "Press Ctrl+C to stop.`n"

& $server @args
