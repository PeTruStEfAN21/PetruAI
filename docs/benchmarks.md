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
