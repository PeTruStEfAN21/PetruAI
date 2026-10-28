# PetruAI — Raport de Benchmark Ziua 1 (Modele Locale pe Hardware Real)

**Data măsurătorilor:** 2026-10-25  
**Hardware:** NVIDIA GeForce RTX 4050 Laptop (6 GB VRAM, 192 GB/s) | 32 GB RAM DDR5 | AMD Ryzen 7 7445HS (6c/12t)  
**Mediu:** Windows 11 | `llama.cpp` b11877 (CUDA 12.4, Flash Attention ON, KV cache `q8_0`, `--jinja` activat)  
**Metodologie:** Același prompt realist de agent de cod (**exact 4.214 tokeni** de context: reguli PetruAI, unelte, handoff și arhitectură) + cerere simplă de tool calling în limba română:  
> *"Verifică starea depozitului git (git status) pentru a vedea ce modificări există în proiect."*

---

## 1. Tabel Comparativ Executiv

| Metrică | Qwen3.5-4B (IQ4_XS) | Qwen3.5-9B (IQ4_XS) | Qwen3.6-35B-A3B (UD-IQ4_XS MoE) |
|---|---|---|---|
| **Mărime disc (GGUF)** | 2.36 GB | 4.75 GB | 16.51 GB |
| **Locație execuție** | 100% în VRAM | **100% în VRAM** | Hibrid (Atenție GPU, Experți MoE în RAM) |
| **VRAM ocupat la rulare** | 2.94 GB / 6.14 GB | **4.89 GB / 6.14 GB** | 2.78 GB / 6.14 GB (+ ~16.5 GB RAM) |
| **Prefill Cold (4.214 tok)** | **2.365 tok/s** (1.78 s) | **1.729 tok/s** (2.44 s) | **155 tok/s** (27.19 s) |
| **Prefill Warm (cu cache)** | < 0.38 s | < 0.50 s | < 1.80 s |
| **Decode (Generare răspuns)** | **52.2 tok/s** | **34.5 tok/s** | **13.5 tok/s** |
| **Latență totală (Wall time)** | **1.98 s** | **4.63 s** | **30.99 s** |
| **Tool Calling (--jinja)** | ✅ Valid (`git_status`) | ✅ Valid (`git_status`) | ✅ Valid (`git_status`) |
| **Format argumente JSON** | `{"verbose": true}` | `{"verbose": false}` | `{"verbose": true}` |
| **Raționament (Chain-of-Thought)** | Română (concis) | Română (structurat) | Engleză (precis) |
| **Scor SWE-bench Verified (Research)** | ~44–45% | ~50–53% | **~70–73%** |

---

## 2. Analiză Detaliată pe Modele

### Tier B-Speed: Qwen3.5-4B (`Qwen3.5-4B.IQ4_XS.gguf`)
* **Prefill:** 2.365 tok/s — procesează 4.000 de tokeni în sub 2 secunde.
* **Decode:** 52.2 tok/s — textul curge aproape instantaneu pe ecran.
* **Consum VRAM:** ~2.9 GB (lasă peste 3 GB liberi pentru context extins de 16k–32k tokeni).
* **Tool Calling:** A selectat imediat funcția `git_status` cu argumente JSON valide, adăugând un raționament scurt în română.
* **Verdict:** Excelent pentru sarcini rapide, căutări, diff-uri simple sau rulare pe baterie. Limitat însă pe refactorizări arhitecturale complexe.

---

### Tier B-Default: Qwen3.5-9B (`Qwen3.5-9B.IQ4_XS.gguf`)
* **Prefill:** 1.729 tok/s — procesează contextul inițial de 4.214 tokeni în doar 2.44 secunde.
* **Decode:** **34.5 tok/s** — foarte aproape de plafonul teoretic al lățimii de bandă GDDR6 (37 tok/s pe bus-ul de 192 GB/s).
* **Consum VRAM:** 4.89 GB — **încape 100% în cei 6 GB VRAM ai RTX 4050**, lăsând 1.25 GB spațiu pentru KV cache `q8_0` la context de 8k–12k.
* **Tool Calling:** A apelat impecabil `git_status` (`{"verbose": false}`), fără halucinații sau caractere parazite în afara formatului JSON.
* **Raționament generat:**
  > *"Utilizatorul vrea să verifice starea depozitului git, așa că voi rula comanda git_status pentru a inspecta fișierele neurmărite, modificate și adăugate."*
* **Latență totală:** **4.63 secunde** pentru întregul ciclu (recepție prompt 4.2k tok -> prefill -> gândire -> generare tool call).
* **Verdict:** **Echilibrul ideal pentru utilizarea de zi cu zi.**

---

### Tier A-Quality: Qwen3.6-35B-A3B (`Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`)
* **Arhitectură:** MoE (35B total / 3B activi per token, 256 experți).
* **Configurație rulată:** `--cpu-moe` (experții rulați în RAM-ul de 32 GB al laptopului, atenția și proiecțiile pe GPU).
* **Prefill:** 155.0 tok/s — durează 27.2 secunde pentru cold prompt-ul de 4.214 tokeni (depășind cu mult viteza estimată în research pentru laptopuri similare, care era de ~66 tok/s).
* **Decode:** **13.5 tok/s** — suficient de fluid pentru citire în timp real (un răspuns de 50 de tokeni durează sub 4 secunde).
* **Consum resurse:** Doar 2.78 GB VRAM pe GPU + ~16.5 GB RAM sistem.
* **Tool Calling:** Răspuns de mare acuratețe, `finish_reason: tool_calls`, argumente JSON valide.
* **Latență totală:** 30.99 secunde la primul apel (redusă masiv la apelurile următoare grație `--cache-prompt`).
* **Verdict:** Putere de raționament de nivel frontieră. Ideal pentru când utilizatorul cere planificare complexă sau rezolvarea de bug-uri dificile unde un model de 9B s-ar bloca.

---

## 3. Recomandare pentru Tier-ul Implicit

Pe baza măsurătorilor obiective din Ziua 1:

1. **Tier Implicit Recomandat: `Qwen3.5-9B`**
   - **De ce:** Răspunsul în **4.6 secunde** (la 34.5 tok/s) oferă experiența interactivă de terminal pe care utilizatorul o așteaptă de la un agent de cod în terminal. Încape 100% în placa video fără să solicite magistrala PCIe/RAM.
   - **Capabilități:** SWE-bench de ~50–53% este mai mult decât capabil pentru editări de cod, generare Dart/Flutter și comenzi de terminal.

2. **Modul „Deep/Plan” (Opt-in sau flag `--quality`): `Qwen3.6-35B-A3B`**
   - Utilizat când utilizatorul rulează sarcini complexe de arhitectură sau când modelul de 9B eșuează la o verificare (`dart analyze`). Latența inițială de ~27s este perfect acceptabilă pentru o gândire profundă.

3. **Modul „Fast/Eco” (Flag `--fast`): `Qwen3.5-4B`**
   - Răspuns în sub 2 secunde (52 tok/s), ideal pentru completări rapide de cod pe baterie.

---

## 4. Dovezi de Execuție & Fisiere de Date

Datele brute în format JSON rezultate din fiecare test sunt stocate în:
* `infra/bench_4b.json`
* `infra/bench_9b.json`
* `infra/bench_35b.json`

Scriptul de reproducere automată este `infra/run_benchmark.py`.

---

## 5. Note demo (2026-10-26)

* `petru --model fast -p "..."` într-un folder gol: serverul 4B a pornit automat (~5 s), modelul a apelat `write_file` + `task_complete`, total 14 s, exit 0, `hello.py` corect.
* Comportament 4B: a scris în rezumat „verificat” fără să ruleze scriptul (nu a apelat `shell` sau `run_checks`). De urmărit la demo-urile e2e; dacă persistă, se întărește promptul BUILD (run_checks obligatoriu înainte de task_complete).
* REPL-ul interactiv (prompt_toolkit) nu a fost exersat automat; de verificat manual (vezi `docs/demo.md`).

## 6. Rezultate demo e2e (2026-10-26, online, utilizator scriptat)

| Demo | Tier | Rezultat | Timp | Observații |
|---|---|---|---|---|
| Python todo CLI | default (9B) | PASS | 115 s | 4 întrebări prin ask_user, plan, 2 fișiere, 3 runde run_checks, commit |
| Flutter counter | default (9B) | PASS | 187 s | 5 întrebări, flutter create în subfolder (acceptat), 5 iterații flutter test, commit |
| TypeScript notes API | default (9B) | FAIL | 431 s | ajunge la teste (vitest+supertest) dar nu reușește izolarea stării între teste în 40 de iterații |
| TypeScript notes API | quality (35B) | TIMEOUT | > 2400 s | depășește timeout-ul pytest de 40 min (13 tok/s); de reluat cu timeout mai mare dacă utilizatorul vrea |

Probleme de harness găsite și reparate pe parcurs: întrebări puse în text în loc de ask_user (prompt), întrebări multiple într-un răspuns până la max_tokens → 500 de la server (retry cu temperatură crescută + prompt), marcaje XML scurse în argumente (sanitizare), proiect creat în subfolder (prompt + run_checks acceptă proiect imbricat), depășirea contextului la 16k (numărare exactă prin /tokenize + compactare forțată), node_modules comis (gitignore implicit la primul commit).

## 7. Index de cod (2026-10-26)

| Măsură | Valoare |
|---|---|
| Repo indexat | PetruAI (acest repo) |
| Fișiere / bucăți | 247 / 1.253 |
| Bucăți cu vectori | 1.226 (EmbeddingGemma 2 Q8_0 pe CPU) |
| Timp total | 122 s |

## 8. Evaluarea modelului de bază pentru poarta de antrenare (Qwen3.5-4B IQ4_XS, 2026-10-26)

| Metrică | Valoare |
|---|---|
| Tool calling valid (20 de cereri fixe) | 1,00 |
| Sarcini reale trecute | 2 din 6 (python_cli_wordcount, python_csv_stats; toate cele 4 Flutter pică) |
| Durata evaluării | 21 min |

## 9. Antrenare QLoRA pe RTX 4050 6 GB (Qwen3.5-4B, 2026-10-26)

Un pas forward+backward pe o secvență, cu LoRA r=16 și gradient checkpointing Unsloth, după instalarea `fla-core`
(nucleele Triton pentru straturile Gated DeltaNet; fără ele PyTorch folosea o implementare de referință care
umplea VRAM-ul și trecea în memoria partajată).

| Lungime | Vârf memorie | Timp |
|---|---|---|
| model încărcat | 3,88 GB | |
| 4.096 tokeni | 4,94 GB | 6 s |
| 6.144 tokeni | 5,41 GB | 20 s |
| 8.960 tokeni | 6,07 GB (depășește VRAM-ul, Windows mută surplusul în RAM) | 62 s |

Concluzie: ~97 % din exemple (sub 6.144 de tokeni) se antrenează în VRAM; cele mai lungi merg de ~10 ori mai lent, dar
se păstrează, cum a cerut utilizatorul. O epocă pe datasetul v3 e estimată la ~3 ore.

## 10. Index de documentație offline (`petru index --docs --no-embed`, 2026-10-26)

| Sursă | Fișiere |
|---|---|
| SDK Flutter (`packages/flutter/lib`) | 718 |
| site-ul Dart | 1.019 |
| `flutter/samples` | 2.290 |
| site-ul Flutter | 2.604 |
| Total | 6.631 fișiere, 50.498 bucăți, 97 s (doar BM25) |

## 11. Dataset v3 (prima noapte, 2026-10-26)

| Măsură | Valoare |
|---|---|
| Exemple din commit-uri (9 repo-uri locale + 42 GitHub) | 1.354 |
| Eliminate ca duplicate (MinHash) | 95 |
| Antrenare / evaluare | 1.197 / 62 |
| Cod (TypeScript 186, Python 105, Dart 65, Go 50, Rust 45, JS 31, Java 19, C/C++ 23, C# 7, shell 14) | ~55 % |
| Documentație și configurări (Markdown 236, YAML 215, necunoscut 186, JSON 33, TOML 31) | ~45 % |

Filtrul de actualizări de versiuni a scos aproape toate commit-urile „bump” (JSON: 183 → 33 față de v1).

## 12. Echipă (35B lider + 4B asistent) vs 35B singur (2026-10-27)

Bench pe 12 proiecte mici-medii în 6 limbaje (`training/runs/bench/bench-2026-10-27.json`). Fiecare proiect are teste
de acceptanță date; trece doar dacă toate trec. Liderul e Qwen3.6-35B-A3B, asistentul Qwen3.5-4B, amândoi local, pe
rând pe același GPU. Limită: 60 de minute pe încercare. Echipa a fost FORȚATĂ să delege (liderul scrie un fișier, apoi
câte o delegare pentru fiecare fișier nou); alegerea liderului între echipă și solo a venit abia după.

| Proiect | 35B singur | Echipă | Delegări |
|---|---|---|---|
| csharp_bank | PASS, 10 min | PASS, 37 min | 3 |
| csharp_rooms | PASS, 35 min | **PASS, 18 min** | 3 |
| go_adventure | PASS, 12 min | PASS, 27 min | 2 |
| go_expr | PASS, 19 min | PASS, 31 min | 3 |
| java_csv | FAIL, 51 min (apeluri de unealtă invalide) | FAIL, timeout | — |
| java_library | PASS, 15 min | PASS, 28 min | 4 |
| python_inventory | PASS, 7 min | PASS, 17 min | 3 |
| python_markdown | PASS, 12 min | FAIL, timeout (buclă infinită în `blocks.py`) | — |
| rust_ini | PASS, 16 min | PASS, 47 min | 3 |
| rust_kvstore | PASS, 51 min | FAIL, timeout | — |
| ts_cache | PASS, 18 min | PASS, 30 min | 2 |
| ts_todo | FAIL, timeout | **PASS, 35 min** | 2 |
| **Total** | **10/12, medie 26 min** | **9/12, medie 37 min** | |

Mediile includ timeout-urile ca 60 de minute.

Control fără delegare (`bench-2026-10-27.no-delegation.json`): prima rulare în echipă a celor două proiecte C#, în care
liderul nu a delegat nimic, a dat aproape același timp ca 35B singur (csharp_bank 9 vs 10 min, csharp_rooms 40 vs
35 min). Atunci s-a introdus delegarea forțată, iar cele două proiecte au fost refăcute (rândurile din tabel).

Concluzii:
- Pe un singur GPU, echipa lucrează pe rând (liderul așteaptă asistentul), deci delegarea nu aduce viteză în sine;
  costul ei e contextul pe care liderul îl dă și îl verifică. Echipa a câștigat de două ori: csharp_rooms (de două
  ori mai repede) și ts_todo (singur a ieșit din timp).
- Delegarea în paralel a fost măsurată separat (27 oct): cu ambele servere active, 4B scade de la 52 la 20 tok/s și
  35B de la 15,5 la 8 tok/s, deci mai prost decât pe rând.
- „Apeluri de unealtă invalide” la java_csv venea din limita de 4.096 tokeni pe răspuns, care tăia fișierele mari la
  jumătate de apel; reparat ulterior (buget = context/4, `write_file` în bucăți).
- Proiectele echipei, cu cine a scris fiecare fișier: `showcase/`.

## 13. Alegerea liderului: echipă sau solo (2026-10-28)

Probă pe proiectul mare `python_tracker` (24 de module, 133 de teste): liderul citește sarcina și testele, apelează
`choose_mode`, apoi proba se oprește (nu construiește nimic).

| Rulare | Înainte/după | Alegere | Timp până la alegere | Motivul liderului |
|---|---|---|---|---|
| `probe-2026-10-28.json` | înainte | solo (1/1) | 6,4 min | „module strâns cuplate, fiecare depinde de celelalte” |
| `probe-2026-10-28b.json` | după `0ce98f7` | echipă (3/3) | 1,5–2 min | „se împarte curat în subpachete independente cu interfețe clare” |

Cauza alegerii solo: `choose_mode` nu era permis în faza DESIGN, așa că liderul își scria întâi planul pentru un singur
agent și apoi alegea modul care se potrivea cu planul. Dependența de modelele și erorile comune era citită drept
cuplare strânsă. După reparație liderul alege înainte de plan, iar criteriul spune că modulele care depind doar de
modele comune nu sunt cuplate (liderul scrie modelele, apoi delegă piesele). Alegerea e acum și de 3–4 ori mai rapidă.

## 14. Proiectul mare python_tracker, echipă vs solo (2026-10-28)

Raport: `training/runs/bench/bench-large-2026-10-28b.json` (180 de minute pe încercare). De completat după rulare.

| Mod | Rezultat | Timp | Delegări | Observații |
|---|---|---|---|---|
| 35B singur | | | | |
| Echipă | | | | |
