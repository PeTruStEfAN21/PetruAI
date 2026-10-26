# Memorie, index de cod și jurnal

Petru învață fără reantrenare în trei feluri: ține minte ce îi spui (memorie), își găsește singur drumul prin cod
(index) și știe ce s-a schimbat recent în proiect (jurnal). Totul e local, în fișiere obișnuite.

## Memorie

| Unde | Ce |
|---|---|
| `<proiect>/.petru/memory/` | fapte despre proiect: convenții, decizii tehnice, unde sunt lucrurile |
| `~/.petru/memory/` | preferințe valabile în orice proiect (limbă, stil, unelte preferate) |

Fiecare director are un `MEMORY.md` (index, câte o linie pe amintire, maximum 200 de linii) și câte un fișier
Markdown pe amintire, cu antet `name`, `description`, `type` (`user`, `feedback`, `project`, `reference`).

- Agentul scrie cu tool-ul `remember` (scope `project` sau `global`) și citește cu `recall`. Ambele merg și în
  faza de design, pentru că nu ating codul.
- Actualizările sunt incrementale: dacă salvezi din nou aceeași amintire, se adaugă un rând datat, nimic nu se
  rescrie. Un model mic nu poate șterge din greșeală ce a învățat.
- Indexurile ajung în promptul de sistem (maximum ~1.500 de tokeni; la depășire pleacă cele mai vechi linii de
  proiect). Secretele (chei, token-uri, parole) sunt refuzate.
- `/memory` în REPL arată ce știe Petru.

Export și import (de exemplu pe alt laptop sau la un prieten):

```powershell
petru memory export petru-memorie.zip                 # global + proiectul curent
petru memory export global.zip --global-only
petru memory import petru-memorie.zip --project D:\proiect
```

Arhiva conține `global/`, `project/memory/`, `project/DECISIONS.md` și `project/journal.sqlite`; indexul de cod nu
se exportă (se reconstruiește). Importul nu suprascrie nimic: o amintire existentă primește doar rândurile care îi
lipsesc, iar un import repetat nu mai schimbă nimic.

## Index de cod (`search_code`)

`<proiect>/.petru/index.sqlite`: fiecare fișier e împărțit cu tree-sitter în bucăți pe definiții (clase, funcții,
metode, tipuri) pentru Python, TypeScript/JavaScript, Dart, Go, Rust, Java, C#, Kotlin, C/C++ și altele; restul
fișierului și limbajele necunoscute intră ca ferestre de 60 de linii. Căutarea combină:

- BM25 (SQLite FTS5), bun pentru identificatori exacți;
- vectori (sqlite-vec) din EmbeddingGemma 2, buni pentru „unde se face X” descris în cuvinte;
- fuziune după rang (reciprocal rank fusion).

Tool-ul `search_code` reîmprospătează indexul incremental (doar fișierele schimbate, după hash) înainte de fiecare
căutare. Vectorii se folosesc doar dacă serverul de embeddings rulează; altfel căutarea merge doar pe BM25.

```powershell
petru index                  # construiește/actualizează indexul proiectului curent (pornește embeddings pe CPU)
petru index --no-embed       # doar BM25, fără server de embeddings
```

Serverul de embeddings este un al doilea `llama-server` (`--embeddings`, port 8082) pe CPU, ca să nu concureze cu
modelul de chat pentru cei 6 GB de VRAM. Măsurat pe acest repo: 247 de fișiere, 1.253 de bucăți, 122 s.

## Documentație offline (`search_docs`)

```powershell
petru index --docs
```

Construiește `~/.petru/docs_index.sqlite` din sursa SDK-ului Flutter instalat (`packages/flutter/lib`, deci API-ul
curent) și din clonele din `infra/offline/docs/` (site-ul Flutter, `flutter/samples`, site-ul Dart). Tool-ul
`search_docs` caută acolo; e remediul pentru API-uri Flutter depreciate pe care modelul le-ar ghici altfel.

Gramaticile tree-sitter se descarcă la prima folosire în `%LOCALAPPDATA%/tree-sitter-language-pack` (tot pachetul
pentru Windows, deci apoi merg toate offline); pe acest laptop sunt deja descărcate. Fără gramatică, un fișier e
indexat pe ferestre. `petru doctor` verifică dacă există.

## Jurnal

`<proiect>/.petru/journal.sqlite` ține:

- **salvările**: `petru watch` urmărește folderul proiectului (VS Code, agentul, `git checkout`, orice) și scrie
  fiecare schimbare ca diff față de ultima versiune; folderele ignorate (`node_modules`, `.venv`, `build`...) sunt
  sărite;
- **commit-urile**: `petru journal hook install` pune un hook `post-commit` care adaugă commit-ul într-o coadă, în
  fundal, fără să întârzie sau să strice vreodată commit-ul (un hook existent e păstrat și apelat înainte);
- **rezumatele**: modelul local scrie 2–4 rânduri „ce s-a schimbat și de ce” pentru fiecare commit din coadă, folosind
  mesajul, diff-ul și fișierele editate între timp. Se scriu leneș: la pornirea REPL-ului (până la 3) sau cu
  `petru journal summarize`.

Ultimele 5 rezumate intră în promptul de sistem; `/journal` le arată pe toate cele recente. Baza de date folosește
WAL, deci REPL-ul și `petru watch` pot scrie în același timp.

```powershell
petru watch                          # Ctrl+C pentru oprire
petru journal hook install           # în proiectul curent
petru journal summarize --model fast
```
