# PetruAI

A local, offline-first coding agent for the terminal, with its own fine-tuning pipeline.
It runs open-weight models through llama.cpp on a 6 GB laptop GPU, asks design questions before writing code,
follows the user's decisions, verifies its work with the project's own tests and commits when they pass.

```mermaid
flowchart LR
    U[User in the terminal] --> R[REPL / petru -p]
    R --> A[Agent loop<br/>DESIGN → plan → BUILD]
    A -->|chat + tool schemas| S[llama-server :8080<br/>Qwen 4B / 9B / 35B / tuned]
    A --> T[Tools: files, shell, git,<br/>run_checks, ask_user, plan]
    A --> M[Memory<br/>.petru/memory, ~/.petru/memory]
    A --> I[search_code / search_docs<br/>FTS5 + sqlite-vec]
    I --> E[llama-server :8082<br/>EmbeddingGemma on CPU]
    W[petru watch + post-commit hook] --> J[Journal<br/>diffs + commit summaries]
    J --> A
    subgraph Nightly training
        D[Your repos + permissive GitHub repos<br/>+ verified agent trajectories] --> Q[QLoRA on Qwen3.5-4B]
        Q --> X[Merge → GGUF → Q4_K_M]
        X --> G{Gate: loss, tool validity,<br/>task pass vs base}
        G -->|no regression| P[Promote as tier tuned]
    end
    P --> S
```

## Why

Cloud coding agents need an internet connection and a subscription. PetruAI is built for working fully offline on a
mid-range laptop (RTX 4050 6 GB, 32 GB RAM), across Python, TypeScript and Flutter/Dart, and for getting better over
time by training on the user's own repositories.

## What it does

- **Two enforced phases.** Every new request starts in a DESIGN phase: the agent may only read the project and ask
  questions (`ask_user`), then proposes a plan. Writing tools unlock only after the user confirms the plan. The
  answers are appended to `.petru/DECISIONS.md` and treated as final. `/quick` skips the questions for small fixes.
- **Tools.** `read_file`, `write_file`, `edit_file` (exact search/replace, refuses ambiguous matches), `list_dir`,
  `glob`, `grep`, `search_code`, `search_docs`, `shell` (PowerShell, timeouts, process-tree kill), `git`,
  `run_checks` (detects pytest, npm test,
  tsc, dart analyze, flutter test), `ask_user`, `plan`, `task_complete`, `remember`, `recall`.
- **Safety.** Paths cannot escape the project root; shell commands are classified safe, unknown or dangerous; anything
  not clearly safe asks for confirmation (`--yolo` disables prompts).
- **Robust tool calling with small models.** Native tool calls with a text fallback (`<tool_call>` tags, JSON
  fences), JSON repair, schema validation, sanitizing of leaked markup, bounded retries with rising temperature,
  exact token counting through the server and transcript compaction that never splits a tool call from its result.
- **Model tiers**, started and health-checked automatically:

  | Tier | Model (GGUF) | Where it runs |
  |---|---|---|
  | `default` | Qwen3.5-9B IQ4_XS | fully in VRAM |
  | `quality` | Qwen3.6-35B-A3B UD-IQ4_XS | MoE experts in system RAM |
  | `fast` | Qwen3.5-4B IQ4_XS | fully in VRAM |
  | `tuned` | Qwen3.5-4B fine-tuned by the pipeline below | appears once a model passes the gate |

- **Offline package caches** for generated projects: a Python wheelhouse, a pre-filled npm cache and a pub cache
  (`infra/offline/`), with the agent told which packages are available.

## Learning without retraining

- **Memory.** `remember` / `recall` write typed Markdown notes (user, feedback, project, reference) to
  `.petru/memory/` and `~/.petru/memory/`; their indexes go into the system prompt. Updates are append-only deltas,
  so a small model cannot erase what it learned. `petru memory export|import` moves them between machines.
- **Code index.** tree-sitter chunks (functions, classes, methods; 20 languages) in SQLite with FTS5 (BM25) and
  sqlite-vec (EmbeddingGemma 2 vectors on a CPU llama-server), fused by reciprocal rank; `search_code` refreshes it
  incrementally before each search. `search_docs` does the same over the Flutter SDK source and offline docs.
- **Journal.** `petru watch` records every save as a diff; a git post-commit hook queues commits, and the local
  model writes a 2–4 line "what and why" summary per commit, shown in the prompt and under `/journal`.

See `docs/memory.md`.

## Training pipeline (`training/`)

An autonomous, resumable nightly pipeline (Python 3.12, Unsloth + TRL):

1. **Data.** Commits of the user's repositories and of 42 permissively licensed GitHub repositories (license
   verified through the GitHub API; copyleft and unknown licenses excluded) become read/edit/complete tool
   trajectories. Filters drop generated files, lockfiles, secrets, trivial messages and oversized changes; MinHash
   deduplication and per-language balancing follow. Verified trajectories of the local models solving scripted tasks
   (kept only when all checks pass) are mixed in. No output of any proprietary model is used.
2. **QLoRA** on Qwen3.5-4B in 4-bit with assistant-only loss, checkpoints, automatic resume and a time budget.
3. **Export**: adapter merge, conversion to GGUF and Q4_K_M quantization.
4. **Gate**: the candidate is promoted only if it does not regress against the base model on held-out loss
   (assistant tokens), tool-call validity on fixed requests and the pass rate on harness tasks.

Each heavy step runs in its own process so the GPU is fully released between steps. See `docs/training.md`.

## Install (Windows, NVIDIA GPU)

```powershell
git clone https://github.com/PeTruStEfAN21/PetruAI.git
cd PetruAI
powershell -ExecutionPolicy Bypass -File infra/setup.ps1 -DryRun   # shows what it would do
powershell -ExecutionPolicy Bypass -File infra/setup.ps1           # installs what is missing
```

The script reads the GPU and RAM, installs `uv`, creates the environment, downloads the llama.cpp `b11877` CUDA
binaries and the models that fit the card (4B always, 9B from ~6 GB VRAM, the 35B MoE with `-IncludeQuality` and
24 GB RAM), puts `petru` on PATH and runs `petru doctor`, which checks every dependency and the offline caches and
prints the fix for anything missing. Details: `docs/setup.md`.

## Quick start

```powershell
py -3.14 -m uv sync
py -3.14 -m uv run petru                     # REPL in the current folder, tier "default"
py -3.14 -m uv run petru --model fast -p "Create hello.py that prints the date"   # one-shot
```

Slash commands: `/help`, `/model [tier]`, `/plan`, `/quick <text>`, `/done`, `/yolo`, `/status`, `/memory`,
`/journal`, `/exit`. Subcommands: `petru index [--docs]`, `petru watch`, `petru journal hook install`,
`petru memory export|import`.

## Tests

```powershell
py -3.14 -m uv run pytest -q                              # agent unit tests
$env:PETRU_E2E = "1"; py -3.14 -m uv run pytest -m e2e    # live demos with the real model and a scripted user
cd training; py -3.14 -m uv run pytest -q                 # training pipeline unit tests
$env:PETRU_GPU = "1"; py -3.14 -m uv run pytest -q -m gpu # GPU tests (QLoRA steps, evaluation)
```

End-to-end demos from an empty folder (design questions, plan, build, checks, commit), measured on the laptop with
the 9B tier: a Python todo CLI with pytest (about 2 minutes) and a Flutter counter app with widget tests (about
3 minutes). Measurements are in `docs/benchmarks.md`.

## Layout

```
petru/        the agent: cli, tui, agent loop, phases and permissions, tools, providers, llama-server manager
training/     dataset building, trajectories, QLoRA training, evaluation gate, GGUF export, nightly orchestrator
infra/        llama.cpp (binaries and models not in git), benchmarks, offline package caches
docs/         benchmarks, demo guide, training guide
research_notes/  notes with sources on local models, agent harnesses, memory and fine-tuning
tests/        unit tests and live end-to-end demos
```

## Status and roadmap

Done: the agent (phases, tools, permissions, TUI, model tiers), the training pipeline, project and global memory
with export/import, the hybrid code index, the offline docs index, the change journal, a one-script setup and
`petru doctor`. Next: the first promoted fine-tuned model.
