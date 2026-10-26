# Instalare (Windows, placă NVIDIA)

## Ce îți trebuie

- Windows 10/11, o placă NVIDIA cu driverul instalat (`nvidia-smi` trebuie să meargă).
- Python 3.14 (`winget install Python.Python.3.14`) și Git.
- Opțional, pentru proiectele pe care le va construi agentul: Node 24, Flutter.
- Spațiu: ~10 GB pentru modelele de bază, ~28 GB cu modelul mare.

## Un singur script

```powershell
git clone https://github.com/PeTruStEfAN21/PetruAI.git
cd PetruAI
powershell -ExecutionPolicy Bypass -File infra/setup.ps1 -DryRun    # arată ce ar face
powershell -ExecutionPolicy Bypass -File infra/setup.ps1            # face
```

Scriptul:

1. citește placa video și memoria (`nvidia-smi`, RAM);
2. verifică Python 3.14 și instalează `uv` dacă lipsește;
3. creează mediul agentului (`uv sync`);
4. descarcă binarele llama.cpp `b11877` pentru CUDA 12 din release-ul oficial, dacă lipsesc;
5. descarcă modelele potrivite plăcii: Qwen3.5-4B și EmbeddingGemma mereu, Qwen3.5-9B de la ~6 GB VRAM în sus,
   Qwen3.6-35B-A3B doar cu `-IncludeQuality` și cel puțin 24 GB RAM; sub 6 GB VRAM, tier-ul implicit devine `fast`;
6. instalează comanda `petru` pe PATH (`uv tool install --editable`);
7. rulează `petru doctor`.

Se poate rula de câte ori vrei: fiecare pas sare peste ce există deja. Opțiuni: `-SkipModels`, `-SkipLlama`.

## `petru doctor`

Verifică tot ce contează și spune cum se repară ce lipsește: Python, uv, llama-server, GPU și VRAM, fiecare model,
git/node/npm/flutter/dart, cache-urile offline (wheel-uri Python, npm, pub), gramaticile tree-sitter, indexul de
documentație, spațiul pe disc, mediul de antrenare și conexiunea. Ieșire 1 dacă ceva împiedică pornirea.

Exemplu pe laptopul de dezvoltare (RTX 4050 6 GB, 32 GB RAM): 20 OK, 1 avertisment (indexul de documentație nu era
construit încă).

## Înainte să rămâi fără internet

```powershell
powershell -File infra/offline/build_caches.ps1     # pachete Python, npm și pub pentru proiectele noi
petru index --docs --no-embed                        # documentația Flutter/Dart offline
petru doctor                                         # totul pe OK
```
