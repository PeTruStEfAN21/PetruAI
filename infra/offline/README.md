# Lucru offline: ce e în cache și cum verifici

Scop: `pip install`, `npm install` și `flutter pub get` să meargă fără internet pentru pachetele din `manifest.toml`.

## Ce există (construit 2026-10-25)
- Python 3.14: `wheels/py314/` — 126 wheel-uri, 108 MB, toate cele 54 de pachete din `[python]` (raport în `wheels_py314_report.json`).
  Instalare offline: `pip install --no-index --find-links infra/offline/wheels/py314 <pachet>`.
- Node 24: cache-ul npm global (`%LOCALAPPDATA%/npm-cache`) umplut prin `npm-template/` (64 de pachete, `package-lock.json` comis).
  Instalare offline: copiază `package.json` + `package-lock.json` din șablon sau folosește aceleași versiuni, apoi `npm install --offline`.
  Fără pachete native: `better-sqlite3` și `bcrypt` cer compilare (Windows SDK lipsă). Folosește `node:sqlite` (inclus în Node 24) și `bcryptjs`.
- Flutter 3.47: cache-ul pub (`%LOCALAPPDATA%/Pub/Cache`) umplut prin `flutter-template/` (42 de pachete, `pubspec.lock` comis); `flutter precache --windows --android --web` rulat.
  Instalare offline: `flutter pub get --offline` într-un proiect cu aceleași pachete (versiunile din `pubspec.lock`).
- Documentație: `docs/` — clone ale `flutter/website`, `flutter/samples`, `dart-lang/site-www` (4,8 GB, gitignored). Sursa SDK-ului Flutter instalat e tot documentație (API-ul curent).

## Reconstruire / verificare
`powershell -NoProfile -ExecutionPolicy Bypass -File infra/offline/build_caches.ps1` — umple cache-urile și apoi verifică în copii temporare cu `npm install --offline` și `flutter pub get --offline`. Rezultatul în `build_caches.log` (toate liniile `exit=0` = bine).
Ultima rulare: 2026-10-25 21:41–21:45, toate cele cinci etape `exit=0`.

## Ce nu e în cache
Pachetele nelistate în `manifest.toml`; tool-uri globale npm (`pnpm`, `yarn`, `create-vite`, `create-next-app`); emulatorul Android (nu există Android SDK pe laptop, Flutter se verifică prin `flutter analyze` + `flutter test`).
