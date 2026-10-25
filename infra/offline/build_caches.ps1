# PetruAI - fills the npm and pub caches from the offline templates, then verifies them with --offline installs.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File infra/offline/build_caches.ps1
$ErrorActionPreference = "Continue"
$PSDefaultParameterValues["Out-File:Encoding"] = "utf8"
$offline = $PSScriptRoot
$root = Split-Path -Parent (Split-Path -Parent $offline)
$log = Join-Path $offline "build_caches.log"
"=== build_caches start $(Get-Date -Format s) ===" | Out-File -FilePath $log -Encoding utf8

Set-Location (Join-Path $offline "npm-template")
"--- npm install (fills npm cache) ---" >> $log
npm install --no-audit --no-fund *>> $log
"npm install exit=$LASTEXITCODE" >> $log
npm cache verify *>> $log

Set-Location (Join-Path $offline "flutter-template")
"--- flutter pub get (fills pub cache) ---" >> $log
flutter pub get *>> $log
"flutter pub get exit=$LASTEXITCODE" >> $log
"--- flutter precache (windows, android, web) ---" >> $log
flutter precache --windows --android --web *>> $log
"flutter precache exit=$LASTEXITCODE" >> $log

$tmp = Join-Path $env:TEMP ("petru-offline-" + (Get-Date -Format yyyyMMddHHmmss))
New-Item -ItemType Directory -Force -Path (Join-Path $tmp "npm") | Out-Null
Copy-Item (Join-Path $offline "npm-template/package.json") (Join-Path $tmp "npm")
if (Test-Path (Join-Path $offline "npm-template/package-lock.json")) { Copy-Item (Join-Path $offline "npm-template/package-lock.json") (Join-Path $tmp "npm") }
Set-Location (Join-Path $tmp "npm")
"--- npm install --offline (temp copy) ---" >> $log
npm install --offline --no-audit --no-fund *>> $log
"npm offline exit=$LASTEXITCODE" >> $log

New-Item -ItemType Directory -Force -Path (Join-Path $tmp "flutter") | Out-Null
Copy-Item (Join-Path $offline "flutter-template/pubspec.yaml") (Join-Path $tmp "flutter")
Copy-Item (Join-Path $offline "flutter-template/pubspec.lock") (Join-Path $tmp "flutter")
Set-Location (Join-Path $tmp "flutter")
"--- flutter pub get --offline (temp copy) ---" >> $log
flutter pub get --offline *>> $log
"flutter offline exit=$LASTEXITCODE" >> $log

Set-Location $root
"=== build_caches end $(Get-Date -Format s) ===" >> $log
Get-Content $log | Select-String -Pattern "exit=|===" | ForEach-Object { $_.Line }
