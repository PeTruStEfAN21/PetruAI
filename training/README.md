# training/ — pipeline-ul de antrenare PetruAI

Mediu separat de cel al agentului: Python 3.12 (Unsloth nu suportă 3.14), gestionat cu `uv`.

## Mediul

```powershell
cd training
py -3.14 -m uv sync --python 3.12        # sau `uv sync` dacă uv e pe PATH; descarcă ~3 GB (torch cu126, unsloth)
py -3.14 -m uv run python -m petru_train.env   # raport: torch, CUDA, bf16, unsloth, încărcarea modelului în 4-bit, VRAM
```

Greutățile de bază: `infra/llama.cpp/models/hf/Qwen3.5-4B/` (safetensors, ~8,8 GB, gitignored), descărcate cu
`huggingface_hub.snapshot_download("Qwen/Qwen3.5-4B")`.

Scriptul de conversie în GGUF (`convert_hf_to_gguf.py` + `gguf-py`) se aduce o singură dată, online, din llama.cpp
la tag-ul `b11877` (același cu binarele din `infra/llama.cpp/bin/`): `py -3.14 training/scripts/fetch_convert_script.py`
→ `infra/llama.cpp/convert/` (gitignored).

## Teste

```powershell
cd training
py -3.14 -m uv run pytest -q                       # testele fără GPU
$env:PETRU_GPU = "1"; py -3.14 -m uv run pytest -q -m gpu   # testele care încarcă modelul pe RTX (oprește llama-server înainte)
py -3.14 -m uv run ruff check .
```

## Structura (se completează pe măsură ce planul avansează)

```
petru_train/   env, samples, commits, filters, dedup, build, repos, trajectories, train, evaluate, export, nightly
config/        dataset.toml, trajectories.toml, qlora-4b.toml
schemas/       tools.json (schemele tool-urilor petru, generate din pachetul agentului)
tasks/         sarcini pentru traiectorii și evaluare (TOML)
corpus/        local_repos.toml, repos.toml (cataloage); raw/ = clone (gitignored)
data/          JSONL-uri generate (gitignored)
runs/          adaptoare, checkpoint-uri, evaluări, state.json (gitignored)
```
