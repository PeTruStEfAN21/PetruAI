# Sarcini pentru traiectorii și evaluare

Fiecare fișier TOML descrie o sarcină pe care agentul `petru` o rezolvă singur, cu un utilizator scriptat:

```toml
name = "python_cli_wordcount"
prompt = "Build a command-line word counter in Python with tests. Ask me your design questions first."
answers = ["...", "..."]        # răspunsurile, în ordinea întrebărilor; când se termină, agentul primește „alege tu”
checks = []                     # comenzi suplimentare față de run_checks (pytest / npm test / tsc / dart analyze / flutter test)
tier = "default"                # modelul-profesor când serverul e pornit de script (quality = 35B, mai lent de ~3 ori)
```

O rulare: `py -3.14 -m uv run python -m petru.trajectory training/tasks/python_cli_wordcount.toml --out result.json`
(din rădăcina repo-ului; `--base-url` refolosește un server deja pornit). `result.json` conține transcriptul complet
(`messages`, `tools`), `passed` (toate verificările au ieșit cu 0), timpul, numărul de tokeni și motivul opririi.

Folosire:
- `petru_train.trajectories` rulează sarcinile de mai multe ori și păstrează doar traiectoriile care trec
  (rejection sampling) ca date de antrenare.
- `petru_train.evaluate` rulează primele N sarcini (sortate după nume) cu modelul de bază și cu candidatul;
  rata de reușită e una din cele trei metrici ale porții de promovare.

12 sarcini: 4 Python, 4 TypeScript, 4 Flutter, toate rezolvabile offline cu cache-urile din `infra/offline/`.
