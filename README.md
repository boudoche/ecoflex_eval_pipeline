# Ecoflex Hackathon Evaluation Pipeline

This repository contains a simple evaluation pipeline for scoring hackathon
responses using either a large language model (LLM) or a heuristic fallback.
The code was designed for the GreenHorizon Ecoflex hackathon but can be
adapted to other scenarios with minimal changes.

## Contents

- `prompts.py` — Defines the rubric and helper functions for building
  prompts and parsing LLM responses.
- `evaluate.py` — Command‐line script to evaluate participant submissions
  against a set of questions.  Supports LLM and heuristic modes.
- `questions.json` — A sample dataset with 40 questions and expected
  answers.
- `submissions/` — Example submission files.  The `team42.json` file
  demonstrates the expected submission format.
- `results/` — When you run the evaluator, results and a summary CSV
  will be saved here (you must create this directory or specify
  another path).
- `server.py` — FastAPI service to accept submissions over HTTP and grade them.
- `ui/index.html` — Minimal drag‑and‑drop web UI that posts submissions to the API.

## Running the Evaluator (CLI)

First, ensure you have Python 3.8 or newer installed.  To evaluate
submissions using the heuristic scorer, run:

```bash
python3 evaluate.py \
    --questions questions.json \
    --submissions_dir submissions \
    --out_dir results
```

To use a large language model for evaluation, set your OpenAI API key in
the environment and pass `--use-llm`:

```bash
export OPENAI_API_KEY=sk-...yourkey...
python3 evaluate.py \
    --questions questions.json \
    --submissions_dir submissions \
    --out_dir results \
    --use-llm
```

The evaluator uses GPT-4o-mini by default for LLM-based scoring.

### Parallelization (CLI)

You can process answers concurrently per submission with `--workers N` (default 1):

```bash
python3 evaluate.py ... --workers 6
```

The implementation uses a thread pool and caps concurrency internally to a safe upper bound.

### Weights and Scoring (CLI)

Scores combine three criteria using weights that default to 30% / 20% / 50%:

- **Completeness** (0.3)
- **Conciseness** (0.2)
- **Correctness** (0.5)

You can override weights via CLI (values are normalized to sum to 1):

```bash
python3 evaluate.py ... \
  --weight-completeness 0.3 \
  --weight-conciseness 0.2 \
  --weight-correctness 0.5
```

Alternatively, use environment variables (also normalized):

```bash
export WEIGHT_COMPLETENESS=0.3
export WEIGHT_CONCISENESS=0.2
export WEIGHT_CORRECTNESS=0.5
```

### Self‑Consistency (CLI)

To reduce variance from a single LLM call, you can enable self‑consistency:

- The evaluator runs multiple LLM calls with small prompt variants
- It aggregates the median for each score (completeness/conciseness/correctness)

Default: 3 runs. Override with CLI or env.

Enable/override with:

```bash
python3 evaluate.py ... --use-llm --sc-runs 5
```

You can also set `SELF_CONSISTENCY_RUNS` in the environment.

### OpenAI concurrency and retries (CLI)

- Global per‑process limit on concurrent OpenAI calls: `OPENAI_CONCURRENCY` (default `6`).
- Automatic retry with exponential backoff and jitter on transient errors (rate limits, 5xx, network).

Example:

```bash
export OPENAI_CONCURRENCY=6
```

## API Server (Auto‑Grading)

A lightweight FastAPI server is provided in `server.py` to accept HTTP submissions and grade them automatically.

### Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run locally

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

- Health check: `GET /health`
- Grade one submission: `POST /grade` with JSON body `{ "answers": [ {"question_id": "Q1", "answer": "..."} ] }`
- Required header: `X-Submission-Token: <team_token>`
- Server enforces `participant_id` from the token mapping.
- Results are written to `results/` and `results/summary.csv` by default. Configure with env vars:
  - `QUESTIONS_PATH` (default: `questions.json`)
  - `RESULTS_DIR` (default: `./results`)

Server behavior:
- Uses LLM by default (`use_llm=true`) with GPT-4o-mini; set `OPENAI_API_KEY` on the server.
- Uses a fixed concurrency for grading (default 6 workers). Set `FIXED_WORKERS` env to adjust server‑side.
- Runs grading on a background threadpool so the event loop stays responsive.
- Self‑consistency default is 3 runs; override via env: `SELF_CONSISTENCY_RUNS` (e.g., 5).
- Supports scoring weights via env: `WEIGHT_COMPLETENESS`, `WEIGHT_CONCISENESS`, `WEIGHT_CORRECTNESS`.
- Requires a submission token header; maps token → team.
- **Max submission size: 5MB (default)**; configure via `MAX_SUBMISSION_SIZE` env (in bytes).
  - Size check happens **immediately** before any token validation or API calls.
  - Client-side (UI) checks file size before upload and displays error if too large.
  - Server returns 413 status code with clear error message if limit exceeded.
- Email confirmation sent AFTER all processing (JSON, CSV, XLSX) is complete.

### Token Management

Configure tokens either via environment or a JSON file:

- Env variable `TEAM_TOKENS` with comma‑separated `token:TeamName` pairs:
  ```bash
  export TEAM_TOKENS="tokA:TeamA,tokB:TeamB"
  ```
- Or a JSON file (path via `TOKENS_PATH`, default `./tokens.json`), format:
  ```json
  { "tokA": "TeamA", "tokB": "TeamB" }
  ```
The server loads both sources at startup; file values override duplicates from env.

UI usage: the page at `/ui` has a token field. The token is sent as `X-Submission-Token` header.

### Deploy on AWS EC2 (quick start)

1. Launch an Ubuntu 22.04/24.04 EC2 instance. Open security group ports 22 (SSH) and 80/443 (HTTP/HTTPS).
2. SSH in and install system deps:
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip nginx
   ```
3. Clone/upload this repo, then inside the project dir:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   export QUESTIONS_PATH=$(pwd)/questions.json
   export RESULTS_DIR=$(pwd)/results
   mkdir -p "$RESULTS_DIR"
   export OPENAI_API_KEY=sk-...yourkey...
   export TEAM_TOKENS="tokA:TeamA,tokB:TeamB"  # or provide TOKENS_PATH JSON
   ```
4. Run the server via systemd (auto‑restart on boot/crash). Example unit file and env file shown earlier. Ensure `TEAM_TOKENS` or `TOKENS_PATH` is present in `/etc/ecoflex.env`.
5. (Optional) Reverse proxy with Nginx on port 80/443 and enable TLS via Certbot (e.g., using a temporary dns like `54-xx-xx-xx-xx.sslip.io`).

## Evaluation & Grading Details

The evaluator produces, for each answer, three criterion scores and an aggregated score:

- **Completeness (0–5)**: coverage of key points from the expected answer.
- **Conciseness (0–5)**: clarity and lack of unnecessary verbosity.
- **Correctness (0–5)**: factual alignment with the expected answer.

The final score is a weighted sum:

- Defaults: completeness 0.3, conciseness 0.2, correctness 0.5 (30% / 20% / 50%).
- Configurable via CLI or environment (normalized automatically).

### Heuristic mode

A lightweight token‑based heuristic computes all three scores without calling the LLM. Useful for testing or when no API key is available.

### LLM mode

- The prompt includes a clear rubric and 0/3/5 **calibration anchors** to stabilize the scale.
- Optional **self‑consistency** aggregates multiple LLM runs by median.
- Temperature is 0.0 to minimize randomness.
- Global OpenAI concurrency limit per process with retries/backoff on transient errors.

### Parallelization

- Within a single submission, answers are graded concurrently (thread pool).
- In the API server, a fixed number of workers is used by default (configurable via `FIXED_WORKERS`).

### Outputs

- Per‑participant JSON is saved in `results/{participant_id}.json`.
- `results/summary.csv` aggregates the per‑question scores and final score.

## Submission Format

Participants should submit a JSON file with the following structure:

```json
{
  "answers": [
    { "question_id": "Q34", "answer": "..." },
    { "question_id": "Q35", "answer": "..." }
  ]
}
```

The server derives `participant_id` from the submission token.

## License

This project is provided as is, without warranty of any kind.  Feel
free to modify and reuse it for your hackathon or educational project.