# Demo PetruAI: cum pornești agentul și cum rulezi cele trei demo-uri

## Pornire

Din rădăcina repo-ului (serverul llama.cpp pornește singur, pe tier-ul cerut):

```powershell
py -3.14 -m uv run petru                      # tier implicit (Qwen3.5-9B), proiect = folderul curent
py -3.14 -m uv run petru --project D:\demo    # alt folder (se creează dacă lipsește)
py -3.14 -m uv run petru --model fast         # Qwen3.5-4B, rapid; --model quality = Qwen3.6-35B-A3B
py -3.14 -m uv run petru -p "..."             # o singură cerere, fără întrebări (mod script), ieșire 0/1
```

Dacă `uv` este pe PATH, `uv run petru` merge la fel. Serverul se oprește la `/exit` dacă l-a pornit `petru`; un server
pornit de altcineva pe portul 8080 este refolosit dacă servește același model, altfel `petru` refuză să pornească.

## Ce vezi pe ecran

1. `Petru ready. phase=idle tier=default project=... offline. /help for commands.` și promptul `petru>`.
2. Scrii cererea. Agentul intră în faza DESIGN: pune 2–5 întrebări, una pe rând (`? Întrebare`, opțiunile numerotate;
   răspunzi cu numărul sau cu text liber). În DESIGN sunt permise doar citiri; nu scrie și nu rulează comenzi.
3. Planul: `Plan: <titlu>`, pașii numerotați, deciziile tale. Răspunzi `c` (sau Enter) = confirmă, `e` = editezi pașii
   (unul pe linie, linie goală = gata), `r` = respingi. Deciziile ajung în `.petru/DECISIONS.md` (append-only, cu dată).
4. Faza BUILD: linii compacte `▸ write_file path=...` / `✓ ...` pentru fiecare tool. Comenzile necunoscute sau
   periculoase cer confirmare: `[y]es / [n]o / [a]lways` (`a` = nu mai întreba pentru tool-ul acela în sesiune).
5. Agentul rulează `run_checks` (pytest / npm test / tsc / dart analyze / flutter test), repară, apoi `task_complete`
   și propune commit prin tool-ul `git`. Faza revine la IDLE; următoarea cerere pornește un nou DESIGN.

Comenzi: `/help`, `/model [tier]`, `/plan`, `/quick <text>` (sare peste întrebări), `/done`, `/yolo`, `/status`, `/exit`.
Ctrl+C în timpul unei ture o anulează (transcriptul rămâne valid); Ctrl+D sau `/exit` închide.

## Cele trei demo-uri (folder gol, Wi-Fi oprit)

| Demo | Cererea | Răspunsurile la întrebări |
|---|---|---|
| Python | `Build a small command-line todo app in Python with tests. Ask me your design questions first.` | `JSON file in the project folder`, `add, list, done, remove`, `pytest`, `yes, commit when green` |
| TypeScript | `Build a small REST API for notes in TypeScript with tests. Ask me your design questions first.` | `Express with TypeScript`, `in-memory array`, `GET /notes, POST /notes, DELETE /notes/:id`, `vitest with supertest`, `yes` |
| Flutter | `Create a small Flutter app from scratch with widget tests. Ask me your design questions first.` | `counter with a reset button and a history list`, `setState, no packages`, `widget tests`, `yes` |

Criteriul de reușită (design §5): proiectul există, verificările trec (`pytest`; `npm test` + `tsc`; `dart analyze` +
`flutter test`) și există cel puțin un commit cu arborele curat.

## Suita e2e (aceleași demo-uri, cu utilizator scriptat)

```powershell
$env:PETRU_E2E = "1"                      # altfel testele e2e sunt sărite
$env:PETRU_E2E_TIER = "default"           # sau quality / fast
$env:PETRU_E2E_OFFLINE = "1"              # opțional: forțează promptul offline chiar cu internet
py -3.14 -m uv run pytest -m e2e tests/e2e -v --timeout=1800
```

Fiecare rulare scrie transcriptul complet (întrebări, tool-uri, mesaje) în `tests/e2e/logs/<test>.json` (gitignored),
util la diagnosticarea unui demo picat. Rezultatele măsurate sunt în `docs/benchmarks.md`, secțiunea „Demo results”.

## Cerințe

- `infra/llama.cpp/bin/llama-server.exe` și modelele din `infra/llama.cpp/models/` (nu sunt în git; se descarcă separat).
- Pentru verificări: `pytest` în Python-ul folosit de proiect (instalat global din `infra/offline/wheels/py314`),
  Node 24 cu cache-ul npm umplut, Flutter 3.47 cu cache-ul pub umplut (`infra/offline/README.md`).
