# Campus Customs

Yale Bulldog Blue shop. React, Vite, and TypeScript in `frontend/`. FastAPI and a PydanticAI agent in `backend/`. The catalogue, inventory, and accounts live in `data/campus_customs.db`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Put `PORTKEY_API_KEY` in `.env`. Optional `LLM_MODEL` defaults to `gpt-5.6-luna`.

From `frontend/`:

```bash
npm install
```

## Run

Backend, from `backend/`:

```bash
../.venv/bin/uvicorn main:app --reload --port 8000
```

Frontend, from `frontend/`:

```bash
npm run dev
```

The shop is at `http://127.0.0.1:5174`. The API is at `http://127.0.0.1:8000`. Product photos are served from `data/products/`.

How the agent, tools, and limits work is in `output/harness.md`.
