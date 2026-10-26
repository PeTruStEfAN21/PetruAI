# Antrenarea PetruAI: cum rulezi o noapte și ce se întâmplă

Pipeline-ul este în `training/` (mediu separat, Python 3.12, `uv`).

## Ce intră în date și de ce este legal

1. **Repo-urile tale** (`training/corpus/local_repos.toml`, 9 repo-uri): fiecare commit devine o traiectorie de
   tool-uri (`read_file` → `edit_file`/`write_file` → `task_complete`) cu mesajul commit-ului ca cerere.
   Filtre: fără merge-uri, fără mesaje banale („wip”, „fix”), fără fișiere generate (lockfile-uri, `dist/`,
   `*.g.dart`...), fără secrete (`.env`, chei, token-uri), cel mult 3 fișiere și 6.000 de caractere per fișier.
2. **Repo-uri GitHub cu licențe permisive** (`training/corpus/repos.toml`, 42 de repo-uri): licența e verificată prin
   GitHub API (`MIT`, `Apache-2.0`, `BSD-2/3`, `ISC`, `0BSD`, `CC0`, `Unlicense`); `NOASSERTION` sau copyleft =
   exclus. Clone superficiale (300 de commit-uri) în `training/corpus/raw/` (gitignored). Proveniența (repo,
   licență, commit) rămâne în fiecare sample.
3. **Traiectorii verificate** ale modelelor locale (Qwen3.5/3.6): agentul `petru` rezolvă sarcinile din
   `training/tasks/` cu un utilizator scriptat; se păstrează doar traiectoriile la care toate verificările
   (pytest / npm test / tsc / dart analyze / flutter test) trec. Niciun output al unui model comercial din cloud nu intră
   în date (anti-goal A2).

Apoi: deduplicare MinHash (5-grame, Jaccard 0,7), echilibrare pe limbaj (niciun limbaj peste 40 %), împărțire
train/eval stratificată (5 % eval). Rezultatul: `training/data/train.jsonl`, `eval.jsonl`, `stats.json`.

## O noapte de antrenare

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File training/run_night.ps1 -Run 2026-10-27 -Hours 7
```

Scriptul oprește orice `llama-server` (eliberează VRAM) și rulează pașii, în ordine:

| Pas | Ce face | Unde lasă rezultatul |
|---|---|---|
| `build` | construiește datasetul (cache per repo) | `training/data/` |
| `trajectories` | rulează sarcinile cu modelul local, păstrează ce trece (3 per sarcină, 4 încercări) | `training/data/trajectories.jsonl` |
| `train` | QLoRA pe Qwen3.5-4B în 4-bit (r=16, α=32, lr 2e-4, 1 epocă, context 4096), checkpoint la 50 de pași, se oprește singur la bugetul de timp | `training/runs/<run>/adapter/` |
| `export` | unește adaptorul (CPU, bf16) → `convert_hf_to_gguf.py` → `llama-quantize` Q4_K_M | `training/runs/<run>/candidate-Q4_K_M.gguf` |
| `eval_base` | o singură dată: cele trei metrici pe modelul de bază | `training/runs/baseline/eval_base.json` |
| `eval_cand` | aceleași metrici pe candidat + decizia porții | `training/runs/<run>/eval_cand.json`, `gate.json` |
| `promote` | doar dacă poarta a trecut: copiază GGUF-ul ca tier `tuned` | `infra/llama.cpp/models/Qwen3.5-4B-petru.gguf` |

Starea e în `training/runs/<run>/state.json`; după o întrerupere (Ctrl+C, pană, buget epuizat) aceeași comandă
reia de la primul pas neterminat. Jurnalul: `training/runs/<run>/nightly.log`.

## Poarta de promovare (anti-goal A4)

Trei numere, bază vs candidat:
- `loss`: pierderea medie pe `eval.jsonl` (trebuie `<=` bază);
- `tool_validity`: din 20 de cereri fixe (`training/eval/tool_requests.json`), câte primesc un apel de tool
  valid (nume cunoscut, argumente JSON) sau un răspuns text când nu e nevoie de tool (toleranță 0,05);
- `task_pass`: rata de reușită pe primele 6 sarcini din `training/tasks/` (trebuie `>=` bază).

Dacă oricare regresează, candidatul rămâne în `training/runs/<run>/` și nimic nu ajunge în `infra/`.

## Folosirea modelului promovat

`petru --model tuned` sau `/model tuned` în REPL; tier-ul apare automat când există fișierul. Revenire:
`infra/llama.cpp/models/Qwen3.5-4B-petru.prev.gguf` păstrează versiunea anterioară (redenumește-l înapoi).
Implicit rămâne `default` (9B); pune `default_tier = "tuned"` în `~/.petru/config.toml` dacă vrei altfel.

## Comenzi utile (din `training/`)

```powershell
py -3.14 -m uv run python -m petru_train.build                        # doar datasetul
py -3.14 -m uv run python -m petru_train.trajectories --tier fast     # doar traiectorii
py -3.14 -m uv run python -m petru_train.train --run runs/smoke --max-steps 20
py -3.14 -m uv run python -m petru_train.evaluate --base              # baseline
py -3.14 -m uv run python -m petru_train.export --run runs/2026-10-27 --promote
py -3.14 -m uv run pytest -q                                          # teste fără GPU
$env:PETRU_GPU = "1"; py -3.14 -m uv run pytest -q -m gpu             # teste cu modelul pe RTX
```

## Pentru prieteni

Același pipeline, pe repo-urile lor: editează `training/corpus/local_repos.toml`, rulează o noapte. Datele brute
și adaptoarele nu se partajează (sunt mari și personale); se partajează GGUF-ul promovat dacă vor.
