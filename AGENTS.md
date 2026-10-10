# AGENTS.md — Yale AI course conventions

Rules that apply to every assignment, lab, and lecture project in this repo. Read this before writing code.

## Project layout

- One folder per unit: `lecture_one/`, `hw1/`, `labs/week2/`, etc. Each folder is self-contained with its own `requirements.txt`, `prompts/`, and `data/` as needed.
- Keep LLM prompts in Markdown files under `prompts/`, not inline in Python strings.
- Prefer small scripts with a `main()` and `if __name__ == "__main__":` guard.

## AI model

- Default LLM: **GPT-5.6-luna**, called through **Portkey** (`portkey_ai` client).
- Read the model name from the `LLM_MODEL` env var, falling back to `gpt-5.6-luna`. Never hardcode a different model without saying why in the code.
- Use structured (JSON) outputs when extracting data; validate the result before writing it to disk.
- Log which model handled each call so runs are reproducible.

## API keys and secrets

- Keys live only in a per-project `.env` file (e.g. `lecture_one/.env`) and are loaded with `python-dotenv` or `os.environ`.
- Required variables: `PORTKEY_API_KEY`, optional `LLM_MODEL`.
- Every project ships a `.env.example` with placeholder values; `.env` itself is gitignored and must never be committed, printed, or pasted into chat, notebooks, or generated HTML.
- If a key is missing, fail fast with a clear message telling the user which variable to set and in which `.env` file.
- Never pass keys as CLI arguments or embed them in URLs.

## App look and feel

Modern black-and-pink theme, used for every Dash app, Plotly chart, and generated HTML dashboard.

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#0b0b0f` | Page background |
| `--surface` | `#16161d` | Cards, panels, table rows |
| `--border` | `#2a2a35` | Dividers, card outlines |
| `--text` | `#f4f4f8` | Primary text |
| `--muted` | `#9a9aab` | Secondary text, axis labels |
| `--accent` | `#ff2d95` | Primary pink: buttons, highlights, main series |
| `--accent-2` | `#ff7ac3` | Secondary pink: hover, second series |
| `--accent-3` | `#c400ff` | Tertiary: gradients, third series |

- Typography: system sans-serif stack (`Inter, -apple-system, Segoe UI, Roboto, sans-serif`), generous spacing, rounded corners (`12px`), subtle shadows. No default Bootstrap look.
- Plotly: use `template="plotly_dark"`, set `paper_bgcolor`/`plot_bgcolor` to `--bg`/`--surface`, and use the pink palette above for traces. Hide gridlines or make them `--border`.
- Keep layouts clean: a title bar, a short row of KPI cards, then charts. Mobile-friendly widths (`max-width: 1200px`, flexible grid).

## Dash run rules

- **Do not use the auto-reloader.** Run with `app.run(debug=False)` or, if you need the debugger, `app.run(debug=True, use_reloader=False)`. The reloader forks a second process and every file edit spawns another server, leaving orphans behind.
- Default port is `8050`. Set `host="127.0.0.1"` unless external access is explicitly required.
- Start the app in the foreground in its own terminal so its output and PID are visible. If backgrounding, record the PID (`python app.py & echo $!`).
- **Stopping the app: kill the whole process tree, not just the port listener.** Killing only what holds `:8050` can leave a parent Python process alive.
  ```bash
  # find every process for this app and kill it
  # (match on the script name only: on macOS the interpreter shows up as
  #  ".../Python.app/Contents/MacOS/Python app.py", so "python3 app.py" won't match)
  pgrep -fl "app.py"
  pkill -f "app.py"
  # or, if you have the PID
  kill <pid>            # then, if still alive after a few seconds:
  kill -9 <pid>
  # verify nothing is left listening
  lsof -i :8050
  ```
- When backgrounding with `nohup ... &`, `$!` may be the wrapper shell, not the Python process. Always confirm the real PID with `pgrep -fl "app.py"` or `lsof -i :8050`.
- Use `python3` (Python 3.9, has portkey-ai installed), not the conda `python` (3.7) that is first on PATH.
- Before launching, check `lsof -i :8050`; if something is already listening, stop it first rather than picking a new port.
- Never run more than one instance of the same app at a time.

## General coding rules

- Python 3.11+, `pathlib` for paths, type hints on public functions.
- Pin dependencies in `requirements.txt` with minimum versions.
- Write outputs (JSON, HTML, CSV) into the project's `data/` or `output/` folder, never into the repo root.
- Do not create README or docs files unless asked; put process notes in a single Markdown file per project (e.g. `process_flow.md`).
